"""Fresh-data paper collection runner for research-only candidates."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.features import FeatureConfig, generate_ohlcv_features
from crypto_trade_research.paper_collector import PaperCollectorConfig, run_paper_collector
from crypto_trade_research.paper_monitoring import (
    PaperMonitoringConfig,
    build_paper_monitoring_report,
)

BINANCE_FAPI_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_FAPI_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"

KlineFetcher = Callable[[str, datetime, datetime, int, str], list[list[object]]]
FundingFetcher = Callable[[str, datetime, datetime, int, str], list[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class ForwardPaperRunConfig:
    run_name: str
    output_dir: Path
    issue_id: str
    epic_id: str
    pack_manifest_path: Path
    symbols: tuple[str, ...]
    lookback_minutes: int
    funding_lookback_hours: int
    feature_set_version: str
    rolling_window: int
    higher_timeframes: tuple[str, ...]
    end_time: datetime | None = None
    kline_limit: int = 1500
    funding_limit: int = 1000
    request_sleep_seconds: float = 0.05
    kline_base_url: str = BINANCE_FAPI_KLINES_URL
    funding_base_url: str = BINANCE_FAPI_FUNDING_URL

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ForwardPaperRunConfig:
        feature = dict(payload["feature"])
        return cls(
            run_name=str(payload["run_name"]),
            output_dir=Path(str(payload["output_dir"])),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            pack_manifest_path=Path(str(payload["pack_manifest_path"])),
            symbols=tuple(str(symbol).upper() for symbol in payload["symbols"]),
            lookback_minutes=int(payload.get("lookback_minutes", 420)),
            funding_lookback_hours=int(payload.get("funding_lookback_hours", 200)),
            feature_set_version=str(feature["feature_set_version"]),
            rolling_window=int(feature.get("rolling_window", 20)),
            higher_timeframes=tuple(str(item) for item in feature.get("higher_timeframes", ())),
            end_time=(
                _parse_timestamp(str(payload["end_time"])) if payload.get("end_time") else None
            ),
            kline_limit=int(payload.get("kline_limit", 1500)),
            funding_limit=int(payload.get("funding_limit", 1000)),
            request_sleep_seconds=float(payload.get("request_sleep_seconds", 0.05)),
            kline_base_url=str(payload.get("kline_base_url", BINANCE_FAPI_KLINES_URL)),
            funding_base_url=str(payload.get("funding_base_url", BINANCE_FAPI_FUNDING_URL)),
        )

    @classmethod
    def from_path(cls, path: Path) -> ForwardPaperRunConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def run_forward_paper_collection(
    config: ForwardPaperRunConfig,
    *,
    fetch_klines: KlineFetcher | None = None,
    fetch_funding: FundingFetcher | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Fetch fresh public data, generate features, and run the paper collector."""

    end_time = _closed_minute(config.end_time or (clock or _utc_now)())
    start_time = end_time - timedelta(minutes=config.lookback_minutes)
    funding_start_time = end_time - timedelta(hours=config.funding_lookback_hours)
    candle_rows = _fetch_candle_rows(
        config,
        start_time,
        end_time,
        fetch_klines or _fetch_binance_klines,
    )
    funding_rows = _fetch_funding_rows(
        config,
        funding_start_time,
        end_time,
        fetch_funding or _fetch_binance_funding,
    )
    feature_frame = generate_ohlcv_features(
        candle_rows,
        FeatureConfig(
            feature_set_version=config.feature_set_version,
            rolling_window=config.rolling_window,
            higher_timeframes=config.higher_timeframes,
        ),
        funding_rate_rows=funding_rows,
    )
    entry_prices = _entry_prices_by_symbol_time(candle_rows)
    latest_decision_time = max(_as_datetime(row["decision_time"]) for row in feature_frame.rows)
    latest_features = [
        _feature_row_with_entry_price(row, entry_prices)
        for row in feature_frame.rows
        if _as_datetime(row["decision_time"]) == latest_decision_time
    ]
    config.output_dir.mkdir(parents=True, exist_ok=True)
    feature_path = config.output_dir / "features.parquet"
    _write_rows_parquet(feature_path, latest_features)
    collector_payload = run_paper_collector(
        PaperCollectorConfig(
            run_name=config.run_name,
            output_dir=config.output_dir,
            issue_id=config.issue_id,
            epic_id=config.epic_id,
            pack_manifest_path=config.pack_manifest_path,
            feature_source_path=feature_path,
            label_source_path=None,
            decision_time=_format_timestamp(latest_decision_time),
            mode="forward_paper",
        )
    )
    pack = _read_json(config.pack_manifest_path)
    cumulative_signals = _merge_signals(
        _existing_signals(config.output_dir / "forward_signals.json"),
        [dict(signal) for signal in collector_payload["signals"]],
    )
    current_ledger = _read_json(config.output_dir / "ledger.json")
    resolved_existing_trades = _resolve_open_trades(
        _existing_trades(config.output_dir / "forward_ledger.json"),
        candle_rows,
        pack,
    )
    cumulative_trades = _merge_trades(
        resolved_existing_trades,
        [dict(trade) for trade in current_ledger.get("trades", ())],
    )
    forward_signals_path = config.output_dir / "forward_signals.json"
    forward_ledger_path = config.output_dir / "forward_ledger.json"
    _write_json(
        forward_signals_path,
        {
            "schema_version": "research.forward-paper-signals.v1",
            "run_name": config.run_name,
            "issue_id": config.issue_id,
            "epic_id": config.epic_id,
            "created_at": _format_timestamp(datetime.now(UTC)),
            "signals": cumulative_signals,
        },
    )
    _write_json(forward_ledger_path, {"trades": cumulative_trades, "metrics": {}})
    monitoring_payload = build_paper_monitoring_report(
        PaperMonitoringConfig(
            report_name=f"{config.run_name}_monitoring",
            output_path=config.output_dir / "monitoring_report.json",
            issue_id=config.issue_id,
            epic_id=config.epic_id,
            pack_manifest_path=config.pack_manifest_path,
            ledger_source_path=forward_ledger_path,
            ledger_strategy_name=config.run_name,
            evidence_type="forward_paper",
        )
    )
    open_trades = [trade for trade in cumulative_trades if trade.get("paper_status") == "open"]
    closed_trades = [trade for trade in cumulative_trades if trade.get("paper_status") == "closed"]
    payload: dict[str, object] = {
        "schema_version": "research.forward-paper-run.v1",
        "run_name": config.run_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "window": {
            "start_time": _format_timestamp(start_time),
            "end_time": _format_timestamp(end_time),
            "funding_start_time": _format_timestamp(funding_start_time),
        },
        "symbols": config.symbols,
        "row_counts": {
            "candles": len(candle_rows),
            "funding": len(funding_rows),
            "latest_features": len(latest_features),
            "cumulative_signals": len(cumulative_signals),
            "cumulative_trades": len(cumulative_trades),
            "open_trades": len(open_trades),
            "closed_trades": len(closed_trades),
        },
        "collector_summary": collector_payload["summary"],
        "monitoring_status": monitoring_payload["monitoring_status"],
        "decision": {
            "live_trading_approved": False,
            "working_model": False,
            "forward_paper_gate_passed": monitoring_payload["decision"][
                "forward_paper_gate_passed"
            ],
        },
    }
    _write_json(config.output_dir / "forward_run.json", payload)
    return payload


def _fetch_candle_rows(
    config: ForwardPaperRunConfig,
    start_time: datetime,
    end_time: datetime,
    fetcher: KlineFetcher,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for symbol in config.symbols:
        page = fetcher(symbol, start_time, end_time, config.kline_limit, config.kline_base_url)
        rows.extend(_normalize_kline(symbol, item) for item in page)
        _sleep(config)
    if not rows:
        raise ValueError("fresh candle fetch returned no rows")
    return rows


def _fetch_funding_rows(
    config: ForwardPaperRunConfig,
    start_time: datetime,
    end_time: datetime,
    fetcher: FundingFetcher,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for symbol in config.symbols:
        page = fetcher(symbol, start_time, end_time, config.funding_limit, config.funding_base_url)
        rows.extend(_normalize_funding(item) for item in page)
        _sleep(config)
    if not rows:
        raise ValueError("fresh funding fetch returned no rows")
    return rows


def _fetch_binance_klines(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    limit: int,
    base_url: str,
) -> list[list[object]]:
    query = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "interval": "1m",
            "startTime": _timestamp_ms(start_time),
            "endTime": _timestamp_ms(end_time),
            "limit": limit,
        }
    )
    request = urllib.request.Request(
        f"{base_url}?{query}",
        headers={"User-Agent": "crypto-trade-research/ct137"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Binance kline response must be a list")
    return [list(item) for item in payload]


def _fetch_binance_funding(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    limit: int,
    base_url: str,
) -> list[dict[str, object]]:
    query = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "startTime": _timestamp_ms(start_time),
            "endTime": _timestamp_ms(end_time),
            "limit": limit,
        }
    )
    request = urllib.request.Request(
        f"{base_url}?{query}",
        headers={"User-Agent": "crypto-trade-research/ct137"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Binance funding response must be a list")
    return [dict(item) for item in payload]


def _normalize_kline(symbol: str, item: list[object]) -> dict[str, object]:
    open_time = _ms_timestamp(item[0])
    close_time = open_time + timedelta(minutes=1)
    return {
        "schema_version": "research.dataset.v1",
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": symbol.upper(),
        "base_asset": symbol.upper().removesuffix("USDT"),
        "quote_asset": "USDT",
        "timeframe": "1m",
        "open_time": open_time,
        "close_time": close_time,
        "source_available_at": close_time,
        "open": _decimal(item[1]),
        "high": _decimal(item[2]),
        "low": _decimal(item[3]),
        "close": _decimal(item[4]),
        "volume": _decimal(item[5]),
        "quote_volume": _decimal(item[7]),
        "number_of_trades": int(item[8]),
        "taker_buy_base_volume": _decimal(item[9]),
        "taker_buy_quote_volume": _decimal(item[10]),
        "data_source": "binance_fapi_klines",
        "source_file": None,
        "checksum": None,
    }


def _normalize_funding(item: dict[str, object]) -> dict[str, object]:
    funding_time = _ms_timestamp(item["fundingTime"])
    return {
        "schema_version": "research.funding_rate.v1",
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": str(item["symbol"]).upper(),
        "funding_time": funding_time,
        "source_available_at": funding_time,
        "funding_rate": _decimal(item["fundingRate"]),
        "mark_price": _decimal(item["markPrice"]) if item.get("markPrice") else None,
        "data_source": "binance_fapi_funding_rate",
    }


def _entry_prices_by_symbol_time(
    candle_rows: list[dict[str, object]],
) -> dict[tuple[str, datetime], float]:
    return {
        (str(row["symbol"]), _as_datetime(row["close_time"])): float(row["close"])
        for row in candle_rows
    }


def _feature_row_with_entry_price(
    row: dict[str, object],
    entry_prices: dict[tuple[str, datetime], float],
) -> dict[str, object]:
    updated = dict(row)
    key = (str(row["symbol"]), _as_datetime(row["decision_time"]))
    updated["entry_price"] = entry_prices[key]
    return updated


def _existing_signals(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [dict(signal) for signal in _read_json(path).get("signals", ())]


def _existing_trades(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [dict(trade) for trade in _read_json(path).get("trades", ())]


def _merge_signals(
    existing: list[dict[str, object]],
    incoming: list[dict[str, object]],
) -> list[dict[str, object]]:
    merged = {str(signal["request_id"]): signal for signal in existing}
    for signal in incoming:
        merged[str(signal["request_id"])] = signal
    return sorted(merged.values(), key=lambda signal: str(signal["request_id"]))


def _merge_trades(
    existing: list[dict[str, object]],
    incoming: list[dict[str, object]],
) -> list[dict[str, object]]:
    merged = {_trade_key(trade): trade for trade in existing}
    for trade in incoming:
        merged[_trade_key(trade)] = trade
    return sorted(
        merged.values(),
        key=lambda trade: (str(trade["decision_time"]), str(trade["symbol"])),
    )


def _resolve_open_trades(
    trades: list[dict[str, object]],
    candle_rows: list[dict[str, object]],
    pack: dict[str, object],
) -> list[dict[str, object]]:
    candles_by_symbol: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in candle_rows:
        candles_by_symbol[str(row["symbol"])].append(row)
    for symbol_rows in candles_by_symbol.values():
        symbol_rows.sort(key=lambda row: _as_datetime(row["close_time"]))
    return [
        _resolve_open_trade(trade, candles_by_symbol.get(str(trade["symbol"]), []), pack)
        for trade in trades
    ]


def _resolve_open_trade(
    trade: dict[str, object],
    candle_rows: list[dict[str, object]],
    pack: dict[str, object],
) -> dict[str, object]:
    if trade.get("paper_status") != "open":
        return trade

    strategy = dict(pack["strategy"])
    exits = dict(strategy.get("exits", {}))
    horizon_bars = int(exits.get("horizon_bars", 12))
    stop_loss_pct = float(exits.get("stop_loss_pct", 0.004))
    round_trip_cost_pct = float(
        dict(strategy.get("cost_model", {})).get("round_trip_cost_pct", 0.0007)
    )
    side = str(strategy.get("side", trade.get("side", "long")))
    decision_time = _parse_timestamp(str(trade["decision_time"]))
    future_rows = [row for row in candle_rows if _as_datetime(row["close_time"]) > decision_time][
        :horizon_bars
    ]
    if not future_rows:
        return trade

    entry_price = float(trade["entry_price"])
    stop_price = float(trade["stop_price"])
    target_price = float(trade["target_price"])
    tie_breaker = str(exits.get("target_stop_tie_breaker", "stop_first"))
    for offset, row in enumerate(future_rows, start=1):
        outcome = _bar_outcome(row, side, stop_price, target_price, tie_breaker)
        if outcome is None:
            continue
        exit_price = target_price if outcome == "target" else stop_price
        return _closed_trade(
            trade,
            exit_reason=outcome,
            exit_time=_as_datetime(row["close_time"]),
            exit_price=exit_price,
            net_r=_net_r(
                exit_price,
                entry_price,
                side,
                stop_loss_pct,
                round_trip_cost_pct,
            ),
            gross_r=_gross_r(exit_price, entry_price, side, stop_loss_pct),
            bars_held=offset,
        )

    if len(future_rows) < horizon_bars:
        return trade

    horizon_row = future_rows[-1]
    exit_price = float(horizon_row["close"])
    return _closed_trade(
        trade,
        exit_reason="horizon_exit",
        exit_time=_as_datetime(horizon_row["close_time"]),
        exit_price=exit_price,
        net_r=_net_r(exit_price, entry_price, side, stop_loss_pct, round_trip_cost_pct),
        gross_r=_gross_r(exit_price, entry_price, side, stop_loss_pct),
        bars_held=horizon_bars,
    )


def _bar_outcome(
    row: dict[str, object],
    side: str,
    stop_price: float,
    target_price: float,
    tie_breaker: str,
) -> str | None:
    high = float(row["high"])
    low = float(row["low"])
    if side == "long":
        stop_hit = low <= stop_price
        target_hit = high >= target_price
    else:
        stop_hit = high >= stop_price
        target_hit = low <= target_price
    if stop_hit and target_hit:
        return "target" if tie_breaker == "target_first" else "stop"
    if target_hit:
        return "target"
    if stop_hit:
        return "stop"
    return None


def _closed_trade(
    trade: dict[str, object],
    *,
    exit_reason: str,
    exit_time: datetime,
    exit_price: float,
    net_r: float,
    gross_r: float,
    bars_held: int,
) -> dict[str, object]:
    updated = dict(trade)
    updated.update(
        {
            "paper_status": "closed",
            "exit_reason": exit_reason,
            "exit_time": _format_timestamp(exit_time),
            "exit_price": exit_price,
            "net_r": net_r,
            "gross_r": gross_r,
            "realized_r_after_costs": net_r,
            "bars_held": bars_held,
        }
    )
    return updated


def _gross_r(exit_price: float, entry_price: float, side: str, stop_loss_pct: float) -> float:
    if side == "long":
        return (exit_price / entry_price - 1) / stop_loss_pct
    return (entry_price / exit_price - 1) / stop_loss_pct


def _net_r(
    exit_price: float,
    entry_price: float,
    side: str,
    stop_loss_pct: float,
    round_trip_cost_pct: float,
) -> float:
    return _gross_r(exit_price, entry_price, side, stop_loss_pct) - (
        round_trip_cost_pct / stop_loss_pct
    )


def _trade_key(trade: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(trade["strategy_name"]),
        str(trade["decision_time"]),
        str(trade["symbol"]),
    )


def _closed_minute(value: datetime) -> datetime:
    normalized = value.astimezone(UTC).replace(second=0, microsecond=0)
    return normalized - timedelta(minutes=1)


def _sleep(config: ForwardPaperRunConfig) -> None:
    if config.request_sleep_seconds > 0:
        time.sleep(config.request_sleep_seconds)


def _timestamp_ms(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def _ms_timestamp(value: object) -> datetime:
    return datetime.fromtimestamp(int(str(value)) / 1000, tz=UTC)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)!r}")
    return value.astimezone(UTC)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _write_rows_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    config = ForwardPaperRunConfig.from_path(args.config)
    payload = run_forward_paper_collection(config)
    print(
        json.dumps({"output_dir": str(config.output_dir), "summary": payload["collector_summary"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
