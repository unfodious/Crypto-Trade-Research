"""Research-only counterfactual outcomes for skipped forward-paper signals."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from crypto_trade_research.paper_forward import (
    BINANCE_FAPI_KLINES_URL,
    _fetch_binance_klines,
    _format_timestamp,
    _normalize_kline,
    _parse_timestamp,
    _resolve_open_trade,
)

SCHEMA_VERSION = "research.forward-skip-counterfactual.v1"

KlineFetcher = Callable[[str, datetime, datetime, int, str], list[list[object]]]


@dataclass(frozen=True, slots=True)
class SkipCounterfactualStreamConfig:
    name: str
    issue_id: str
    forward_signals_path: Path
    pack_manifest_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SkipCounterfactualStreamConfig:
        return cls(
            name=str(payload["name"]),
            issue_id=str(payload["issue_id"]),
            forward_signals_path=Path(str(payload["forward_signals_path"])),
            pack_manifest_path=Path(str(payload["pack_manifest_path"])),
        )


@dataclass(frozen=True, slots=True)
class SkipCounterfactualConfig:
    report_name: str
    issue_id: str
    epic_id: str
    output_json_path: Path
    output_markdown_path: Path
    streams: tuple[SkipCounterfactualStreamConfig, ...]
    kline_limit: int = 1500
    request_sleep_seconds: float = 0.05
    kline_base_url: str = BINANCE_FAPI_KLINES_URL

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SkipCounterfactualConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            streams=tuple(
                SkipCounterfactualStreamConfig.from_dict(dict(item)) for item in payload["streams"]
            ),
            kline_limit=int(payload.get("kline_limit", 1500)),
            request_sleep_seconds=float(payload.get("request_sleep_seconds", 0.05)),
            kline_base_url=str(payload.get("kline_base_url", BINANCE_FAPI_KLINES_URL)),
        )

    @classmethod
    def from_path(cls, path: Path) -> SkipCounterfactualConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_forward_skip_counterfactual_report(
    config: SkipCounterfactualConfig,
    *,
    fetch_klines: KlineFetcher | None = None,
) -> dict[str, object]:
    """Simulate skipped forward signals without changing paper ledgers."""

    if not config.streams:
        raise ValueError("streams must not be empty")
    fetcher = fetch_klines or _fetch_binance_klines
    stream_reports = [_stream_report(config, stream, fetcher) for stream in config.streams]
    all_trades = [
        trade
        for stream_report in stream_reports
        for trade in stream_report["counterfactual_trades"]
    ]
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "streams": stream_reports,
        "aggregate": _metrics(all_trades),
        "decision": {
            "research_only": True,
            "live_trading_approved": False,
            "working_model": False,
            "notes": (
                "Counterfactual skipped-signal replay only. It must not alter forward ledgers "
                "or relax live/paper gates."
            ),
        },
    }
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _stream_report(
    config: SkipCounterfactualConfig,
    stream: SkipCounterfactualStreamConfig,
    fetcher: KlineFetcher,
) -> dict[str, object]:
    pack = _read_json(stream.pack_manifest_path)
    signals = _skipped_signals(_read_json(stream.forward_signals_path))
    trades = [
        _simulate_signal(config, stream, pack, signal, fetcher)
        for signal in signals
        if _has_prices(signal)
    ]
    return {
        "name": stream.name,
        "issue_id": stream.issue_id,
        "forward_signals_path": str(stream.forward_signals_path),
        "pack_manifest_path": str(stream.pack_manifest_path),
        "signal_count": len(signals),
        "eligible_signal_count": sum(1 for signal in signals if _has_prices(signal)),
        "ineligible_signal_count": sum(1 for signal in signals if not _has_prices(signal)),
        "counterfactual_trades": trades,
        "metrics": _metrics(trades),
    }


def _skipped_signals(payload: dict[str, object]) -> list[dict[str, object]]:
    signals = [dict(signal) for signal in payload.get("signals", ())]
    return [
        signal
        for signal in signals
        if signal.get("recommended_action") == "skip"
        and "expected_r_below_threshold" in set(signal.get("reason_codes", ()))
    ]


def _has_prices(signal: dict[str, object]) -> bool:
    return all(signal.get(key) is not None for key in ("entry_price", "stop_price", "target_price"))


def _simulate_signal(
    config: SkipCounterfactualConfig,
    stream: SkipCounterfactualStreamConfig,
    pack: dict[str, object],
    signal: dict[str, object],
    fetcher: KlineFetcher,
) -> dict[str, object]:
    decision_time = _parse_timestamp(str(signal["signal_timestamp"]))
    horizon_bars = int(dict(dict(pack["strategy"]).get("exits", {})).get("horizon_bars", 12))
    end_time = decision_time + timedelta(minutes=horizon_bars + 2)
    raw_rows = fetcher(
        str(signal["symbol"]),
        decision_time,
        end_time,
        config.kline_limit,
        config.kline_base_url,
    )
    if config.request_sleep_seconds > 0:
        time.sleep(config.request_sleep_seconds)
    candle_rows = [_normalize_kline(str(signal["symbol"]), row) for row in raw_rows]
    trade = {
        "strategy_name": f"{stream.name}_skip_counterfactual",
        "decision_time": signal["signal_timestamp"],
        "symbol": signal["symbol"],
        "timeframe": signal["timeframe"],
        "side": str(dict(pack["strategy"]).get("side", "long")),
        "model_id": signal.get("model_id"),
        "model_version": signal.get("model_version"),
        "artifact_hash": signal.get("artifact_hash"),
        "expected_r": signal.get("expected_r"),
        "target_before_stop_probability": signal.get("target_before_stop_probability"),
        "rank": signal.get("rank"),
        "feature_freshness_seconds": signal.get("feature_freshness_seconds"),
        "funding_source_latency_seconds": signal.get("funding_source_latency_seconds"),
        "entry_price": signal["entry_price"],
        "stop_price": signal["stop_price"],
        "target_price": signal["target_price"],
        "paper_status": "open",
        "live_order_authority": False,
        "counterfactual_source_action": "skip",
        "counterfactual_source_reasons": list(signal.get("reason_codes", ())),
        "counterfactual_source_blocks": list(signal.get("hard_risk_blocks", ())),
    }
    return _resolve_open_trade(trade, candle_rows, pack)


def _metrics(trades: list[dict[str, object]]) -> dict[str, object]:
    closed = [
        trade
        for trade in trades
        if trade.get("paper_status") == "closed" and trade.get("net_r") is not None
    ]
    net_r_values = [float(trade["net_r"]) for trade in closed]
    positive = [value for value in net_r_values if value > 0]
    negative = [value for value in net_r_values if value < 0]
    reason_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    exit_counts: Counter[str] = Counter()
    for trade in trades:
        symbol_counts[str(trade.get("symbol", ""))] += 1
        if trade.get("exit_reason"):
            exit_counts[str(trade["exit_reason"])] += 1
        for reason in trade.get("counterfactual_source_reasons", ()):
            reason_counts[str(reason)] += 1
    return {
        "signal_count": len(trades),
        "closed_trade_count": len(closed),
        "open_trade_count": len(trades) - len(closed),
        "average_r_after_costs": _mean(net_r_values),
        "median_r_after_costs": _median(net_r_values),
        "win_rate": (len(positive) / len(closed)) if closed else 0.0,
        "profit_factor": (sum(positive) / abs(sum(negative))) if negative else 0.0,
        "average_expected_r": _mean(
            [float(trade["expected_r"]) for trade in trades if trade.get("expected_r") is not None]
        ),
        "exit_reasons": dict(sorted(exit_counts.items())),
        "source_reasons": dict(sorted(reason_counts.items())),
        "symbols": dict(sorted(symbol_counts.items())),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[midpoint]
    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        "Research-only skipped-signal counterfactual. It does not modify paper ledgers "
        "and does not approve live trading.",
        "",
        "## Aggregate",
        "",
        _metrics_lines(dict(payload["aggregate"])),
        "",
        "## Streams",
        "",
        "| stream | signals | closed | avg R | median R | win rate | exits |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for stream in payload["streams"]:
        item = dict(stream)
        metrics = dict(item["metrics"])
        lines.append(
            "| "
            f"`{item['name']}` | "
            f"{int(metrics['signal_count'])} | "
            f"{int(metrics['closed_trade_count'])} | "
            f"{float(metrics['average_r_after_costs']):.4f} | "
            f"{float(metrics['median_r_after_costs']):.4f} | "
            f"{float(metrics['win_rate']):.2%} | "
            f"`{metrics['exit_reasons']}` |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "This is diagnostic evidence only. Keep forward-paper gates unchanged unless "
            "a separate validated issue proves that the skipped-signal population has "
            "positive expectancy.",
            "",
        ]
    )
    return "\n".join(lines)


def _metrics_lines(metrics: dict[str, object]) -> str:
    return "\n".join(
        [
            f"- signals: `{metrics['signal_count']}`",
            f"- closed trades: `{metrics['closed_trade_count']}`",
            f"- open trades: `{metrics['open_trade_count']}`",
            f"- average R after costs: `{float(metrics['average_r_after_costs']):.4f}`",
            f"- median R after costs: `{float(metrics['median_r_after_costs']):.4f}`",
            f"- win rate: `{float(metrics['win_rate']):.2%}`",
            f"- profit factor: `{float(metrics['profit_factor']):.4f}`",
            f"- exit reasons: `{metrics['exit_reasons']}`",
            f"- source reasons: `{metrics['source_reasons']}`",
        ]
    )


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    payload = build_forward_skip_counterfactual_report(
        SkipCounterfactualConfig.from_path(args.config)
    )
    print(json.dumps({"output": payload["report_name"], "aggregate": payload["aggregate"]}))


if __name__ == "__main__":
    main()
