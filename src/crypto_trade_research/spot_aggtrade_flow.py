"""Targeted Binance Spot aggTrades diagnostics around spot replay entries."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from crypto_trade_research.spot_drawdown_swing import (
    SpotDrawdownSwingConfig,
    build_spot_drawdown_swing_positions,
)

SCHEMA_VERSION = "research.spot-aggtrade-flow.v1"
DATA_VISION_BASE_URL = "https://data.binance.vision"
ZipFetcher = Callable[[str], bytes]


@dataclass(frozen=True, slots=True)
class SpotAggTradeFlowConfig:
    report_name: str
    issue_id: str
    epic_id: str
    source_spot_config_path: Path
    output_json_path: Path
    output_markdown_path: Path
    cache_dir: Path
    scenario_names: tuple[str, ...]
    lookback_minutes: int = 30
    base_url: str = DATA_VISION_BASE_URL
    max_candidates: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SpotAggTradeFlowConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            source_spot_config_path=Path(str(payload["source_spot_config_path"])),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            cache_dir=Path(str(payload.get("cache_dir", "data/generated/binance_aggtrades_cache"))),
            scenario_names=tuple(str(item) for item in payload["scenario_names"]),
            lookback_minutes=int(payload.get("lookback_minutes", 30)),
            base_url=str(payload.get("base_url", DATA_VISION_BASE_URL)),
            max_candidates=_optional_int(payload.get("max_candidates")),
        )

    @classmethod
    def from_path(cls, path: Path) -> SpotAggTradeFlowConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_spot_aggtrade_flow_report(
    config: SpotAggTradeFlowConfig,
    *,
    fetch_zip: ZipFetcher | None = None,
    candidate_rows: Sequence[dict[str, object]] | None = None,
) -> dict[str, object]:
    if config.lookback_minutes <= 0:
        raise ValueError("lookback_minutes must be positive")
    fetcher = fetch_zip or _fetch_url_bytes
    candidates = (
        list(candidate_rows)
        if candidate_rows is not None
        else _candidate_positions_from_config(config)
    )
    candidates = sorted(candidates, key=_candidate_sort_key)
    if config.max_candidates is not None:
        candidates = candidates[: config.max_candidates]

    daily_cache: dict[tuple[str, date], list[dict[str, object]]] = {}
    enriched_rows = [
        _enrich_candidate(config, candidate, daily_cache, fetcher) for candidate in candidates
    ]
    scenarios = _scenario_reports(enriched_rows)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "source_spot_config_path": str(config.source_spot_config_path),
        "scenario_names": list(config.scenario_names),
        "lookback_minutes": config.lookback_minutes,
        "candidate_count": len(enriched_rows),
        "source_day_count": len(daily_cache),
        "scenarios": scenarios,
        "decision": _decision(scenarios),
    }
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _candidate_positions_from_config(config: SpotAggTradeFlowConfig) -> list[dict[str, object]]:
    spot_config = SpotDrawdownSwingConfig.from_path(config.source_spot_config_path)
    return build_spot_drawdown_swing_positions(
        spot_config,
        scenario_names=set(config.scenario_names),
    )


def _enrich_candidate(
    config: SpotAggTradeFlowConfig,
    candidate: dict[str, object],
    daily_cache: dict[tuple[str, date], list[dict[str, object]]],
    fetch_zip: ZipFetcher,
) -> dict[str, object]:
    symbol = str(candidate["symbol"]).upper()
    entry_time = _as_datetime(candidate["entry_time"])
    source_day = entry_time.date()
    key = (symbol, source_day)
    if key not in daily_cache:
        daily_cache[key] = _load_daily_aggtrades(config, symbol, source_day, fetch_zip)
    window_start = entry_time - timedelta(minutes=config.lookback_minutes)
    trades = [
        trade
        for trade in daily_cache[key]
        if window_start <= _as_datetime(trade["trade_time"]) <= entry_time
    ]
    metrics = _aggtrade_metrics(trades)
    return {
        "scenario": candidate.get("scenario", ""),
        "window": candidate.get("window", ""),
        "symbol": symbol,
        "entry_time": _format_timestamp(entry_time),
        "status": candidate.get("status", ""),
        "exit_reason": candidate.get("exit_reason", ""),
        "net_return_pct": _as_float(candidate.get("net_return_pct", 0.0)),
        **metrics,
    }


def _load_daily_aggtrades(
    config: SpotAggTradeFlowConfig,
    symbol: str,
    source_day: date,
    fetch_zip: ZipFetcher,
) -> list[dict[str, object]]:
    zip_bytes = _cached_daily_zip(config, symbol, source_day, fetch_zip)
    source_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(
                f"aggTrades zip must contain exactly one CSV for {symbol} {source_day}"
            )
        with archive.open(csv_names[0]) as handle:
            text_handle = io.TextIOWrapper(handle, encoding="utf-8")
            reader = csv.reader(text_handle)
            for fields in reader:
                if not fields:
                    continue
                if not fields[0].isdigit():
                    continue
                row = _aggtrade_fields_to_row(fields)
                normalized = _normalize_aggtrade_row(row, symbol)
                normalized["source_sha256"] = source_sha256
                rows.append(normalized)
    return rows


def _aggtrade_fields_to_row(fields: list[str]) -> dict[str, str]:
    if len(fields) < 8:
        raise ValueError("aggTrades row must have at least 8 fields")
    return {
        "agg_trade_id": fields[0],
        "price": fields[1],
        "quantity": fields[2],
        "first_trade_id": fields[3],
        "last_trade_id": fields[4],
        "transact_time": fields[5],
        "is_buyer_maker": fields[6],
        "is_best_match": fields[7],
    }


def _cached_daily_zip(
    config: SpotAggTradeFlowConfig,
    symbol: str,
    source_day: date,
    fetch_zip: ZipFetcher,
) -> bytes:
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{symbol}-aggTrades-{source_day.isoformat()}.zip"
    path = config.cache_dir / file_name
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    url = f"{config.base_url}/data/spot/daily/aggTrades/{symbol}/{file_name}"
    payload = fetch_zip(url)
    path.write_bytes(payload)
    return payload


def _normalize_aggtrade_row(row: dict[str, str], symbol: str) -> dict[str, object]:
    price = float(_first_present(row, "price", "p"))
    quantity = float(_first_present(row, "quantity", "q"))
    is_buyer_maker = _parse_bool(_first_present(row, "is_buyer_maker", "m"))
    return {
        "symbol": symbol,
        "trade_time": _binance_timestamp(_first_present(row, "transact_time", "T")),
        "price": price,
        "quantity": quantity,
        "notional": price * quantity,
        "is_aggressive_buy": not is_buyer_maker,
    }


def _aggtrade_metrics(trades: Sequence[dict[str, object]]) -> dict[str, object]:
    notionals = [_as_float(trade["notional"]) for trade in trades]
    total_notional = sum(notionals)
    buy_notionals = [
        _as_float(trade["notional"]) for trade in trades if bool(trade["is_aggressive_buy"])
    ]
    sell_notional = total_notional - sum(buy_notionals)
    threshold = _percentile(notionals, 0.95)
    large_trades = [trade for trade in trades if _as_float(trade["notional"]) >= threshold]
    large_buy_notional = sum(
        _as_float(trade["notional"]) for trade in large_trades if bool(trade["is_aggressive_buy"])
    )
    large_total_notional = sum(_as_float(trade["notional"]) for trade in large_trades)
    buy_notional = sum(buy_notionals)
    return {
        "aggtrade_count": len(trades),
        "aggtrade_notional_usd": total_notional,
        "aggtrade_buy_notional_usd": buy_notional,
        "aggtrade_sell_notional_usd": sell_notional,
        "aggtrade_buy_ratio": buy_notional / total_notional if total_notional else 0.0,
        "aggtrade_imbalance": (
            (buy_notional - sell_notional) / total_notional if total_notional else 0.0
        ),
        "large_trade_threshold_usd": threshold,
        "large_trade_count": len(large_trades),
        "large_buy_notional_usd": large_buy_notional,
        "large_buy_ratio": (
            large_buy_notional / large_total_notional if large_total_notional else 0.0
        ),
        "max_trade_notional_usd": max(notionals) if notionals else 0.0,
    }


def _scenario_reports(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["scenario"])].append(dict(row))
    return [_scenario_report(name, grouped[name]) for name in sorted(grouped)]


def _scenario_report(name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    thresholds = [
        ("buy_ratio_55", "aggtrade_buy_ratio", 0.55),
        ("buy_ratio_60", "aggtrade_buy_ratio", 0.60),
        ("imbalance_10", "aggtrade_imbalance", 0.10),
        ("large_buy_ratio_60", "large_buy_ratio", 0.60),
        ("large_buy_ratio_70", "large_buy_ratio", 0.70),
    ]
    slices = [
        _slice_report(label, rows, field, threshold) for label, field, threshold in thresholds
    ]
    return {
        "name": name,
        "candidate_count": len(rows),
        **_metrics(rows),
        "slices": slices,
        "best_slice": _best_slice(slices),
    }


def _slice_report(
    label: str,
    rows: Sequence[dict[str, object]],
    field: str,
    threshold: float,
) -> dict[str, object]:
    selected = [row for row in rows if _as_float(row[field]) >= threshold]
    return {
        "name": label,
        "field": field,
        "threshold": threshold,
        "selected_count": len(selected),
        **_metrics(selected),
    }


def _metrics(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    returns = [_as_float(row["net_return_pct"]) for row in rows]
    positive = [value for value in returns if value > 0]
    return {
        "average_net_return_pct": _mean(returns),
        "median_net_return_pct": _median(returns),
        "positive_rate": len(positive) / len(returns) if returns else 0.0,
        "average_buy_ratio": _mean([_as_float(row["aggtrade_buy_ratio"]) for row in rows]),
        "average_imbalance": _mean([_as_float(row["aggtrade_imbalance"]) for row in rows]),
        "average_large_buy_ratio": _mean([_as_float(row["large_buy_ratio"]) for row in rows]),
    }


def _best_slice(slices: Sequence[dict[str, object]]) -> dict[str, object] | None:
    viable = [row for row in slices if int(row["selected_count"]) >= 10]
    if not viable:
        return None
    return max(viable, key=lambda row: _as_float(row["average_net_return_pct"]))


def _decision(scenarios: Sequence[dict[str, object]]) -> dict[str, object]:
    useful = []
    for scenario in scenarios:
        best = scenario.get("best_slice")
        if not isinstance(best, dict):
            continue
        if (
            _as_float(best["average_net_return_pct"])
            > _as_float(scenario["average_net_return_pct"])
            and int(best["selected_count"]) >= 30
        ):
            useful.append({"scenario": scenario["name"], "slice": best["name"]})
    return {
        "promote_to_paper": False,
        "working_model": False,
        "live_trading_approved": False,
        "useful_slices": useful,
        "notes": (
            "Research-only targeted aggTrades diagnostic; a useful slice still requires "
            "replay validation."
        ),
    }


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        f"Issue: `{payload['issue_id']}`",
        "",
        f"Candidates: `{payload['candidate_count']}`",
        "",
        "## Scenarios",
        "",
        (
            "| Scenario | Candidates | Avg R | Median R | Positive | Avg buy | "
            "Avg imbalance | Avg large buy | Best slice |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        best = item.get("best_slice")
        best_text = "-"
        if isinstance(best, dict):
            best_text = (
                f"{best['name']} ({best['selected_count']}, {_pct(best['average_net_return_pct'])})"
            )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["name"]),
                    str(item["candidate_count"]),
                    _pct(item["average_net_return_pct"]),
                    _pct(item["median_net_return_pct"]),
                    _pct(item["positive_rate"]),
                    _pct(item["average_buy_ratio"]),
                    _pct(item["average_imbalance"]),
                    _pct(item["average_large_buy_ratio"]),
                    best_text,
                ]
            )
            + " |"
        )
    lines.extend(
        ["", "## Decision", "", f"```json\n{json.dumps(payload['decision'], indent=2)}\n```", ""]
    )
    return "\n".join(lines)


def _candidate_sort_key(row: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row.get("scenario", "")),
        str(row.get("window", "")),
        str(row.get("symbol", "")),
        str(row.get("entry_time", "")),
    )


def _fetch_url_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "crypto-trade-research/ct198"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return bytes(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise FileNotFoundError(url) from error
        raise


def _first_present(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row and row[name] != "":
            return row[name]
    raise ValueError(f"missing aggTrades field: {names[0]}")


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1"}


def _binance_timestamp(value: str) -> datetime:
    timestamp = int(value)
    divisor = 1_000_000 if timestamp > 10_000_000_000_000 else 1_000
    return datetime.fromtimestamp(timestamp / divisor, tz=UTC)


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(max(math.ceil(len(ordered) * quantile) - 1, 0), len(ordered) - 1)
    return ordered[index]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _as_float(value: object) -> float:
    return float(value)  # type: ignore[arg-type]


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)  # type: ignore[arg-type]


def _pct(value: object) -> str:
    return f"{_as_float(value) * 100:.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    build_spot_aggtrade_flow_report(SpotAggTradeFlowConfig.from_path(args.config))


if __name__ == "__main__":
    main()
