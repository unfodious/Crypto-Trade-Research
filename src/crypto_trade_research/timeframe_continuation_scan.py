"""Scan higher-timeframe confirmation filters over accepted replay trades."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from crypto_trade_research.backtest import BacktestConfig, SignalRow, evaluate_signal_strategy

SCHEMA_VERSION = "research.timeframe-continuation-scan.v1"


@dataclass(frozen=True, slots=True)
class TimeframeWindowConfig:
    name: str
    replay_report_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TimeframeWindowConfig:
        return cls(
            name=str(payload["name"]),
            replay_report_path=Path(str(payload["replay_report_path"])),
        )


@dataclass(frozen=True, slots=True)
class FeatureFilter:
    feature: str
    operator: str
    value: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FeatureFilter:
        return cls(
            feature=str(payload["feature"]),
            operator=str(payload["operator"]),
            value=float(payload["value"]),
        )


@dataclass(frozen=True, slots=True)
class TimeframeScenario:
    name: str
    description: str
    max_trades_per_day: int | None = None
    allowed_symbols: tuple[str, ...] = ()
    feature_filters: tuple[FeatureFilter, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TimeframeScenario:
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            max_trades_per_day=_optional_int(payload.get("max_trades_per_day")),
            allowed_symbols=tuple(str(item) for item in payload.get("allowed_symbols", [])),
            feature_filters=tuple(
                FeatureFilter.from_dict(dict(item)) for item in payload.get("feature_filters", [])
            ),
        )


@dataclass(frozen=True, slots=True)
class TimeframeContinuationScanConfig:
    report_name: str
    issue_id: str
    epic_id: str
    output_json_path: Path
    output_markdown_path: Path
    target_runner_r: float
    windows: tuple[TimeframeWindowConfig, ...]
    scenarios: tuple[TimeframeScenario, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TimeframeContinuationScanConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            target_runner_r=float(payload.get("target_runner_r", 3.0)),
            windows=tuple(
                TimeframeWindowConfig.from_dict(dict(item)) for item in payload["windows"]
            ),
            scenarios=tuple(
                TimeframeScenario.from_dict(dict(item)) for item in payload["scenarios"]
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> TimeframeContinuationScanConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_timeframe_continuation_scan_report(
    config: TimeframeContinuationScanConfig,
) -> dict[str, object]:
    """Build a report for higher-timeframe filters over accepted replay trades."""

    if config.target_runner_r <= 0:
        raise ValueError("target_runner_r must be positive")
    if not config.scenarios:
        raise ValueError("scenarios must not be empty")

    base_rows = _load_base_rows(config.windows, config.scenarios)
    scenarios = [_scenario_report(config, scenario, base_rows) for scenario in config.scenarios]
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "target_runner_r": config.target_runner_r,
        "windows": [
            {"name": window.name, "replay_report_path": str(window.replay_report_path)}
            for window in config.windows
        ],
        "scenarios": scenarios,
        "decision": _decision(scenarios),
    }
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _load_base_rows(
    windows: tuple[TimeframeWindowConfig, ...],
    scenarios: tuple[TimeframeScenario, ...],
) -> list[dict[str, object]]:
    symbols = sorted({symbol for scenario in scenarios for symbol in scenario.allowed_symbols})
    if not symbols:
        raise ValueError("at least one scenario must declare allowed_symbols")

    feature_names = sorted(
        {
            feature_filter.feature
            for scenario in scenarios
            for feature_filter in scenario.feature_filters
        }
    )
    feature_columns = ["symbol", "timeframe", "decision_time", *feature_names]
    output_rows: list[dict[str, object]] = []
    for window in windows:
        replay_report = _read_json(window.replay_report_path)
        accepted_rows = _accepted_rows_for_window(window, replay_report, symbols)
        if not accepted_rows:
            continue
        wanted_keys = {
            (str(row["symbol"]), str(row["timeframe"]), _as_datetime(row["decision_time"]))
            for row in accepted_rows
        }
        feature_rows = _feature_rows_for_keys(
            Path(str(dict(replay_report["feature_cache"])["rows_path"])),
            feature_columns,
            wanted_keys,
            symbols,
        )
        for row in accepted_rows:
            key = (str(row["symbol"]), str(row["timeframe"]), _as_datetime(row["decision_time"]))
            features = feature_rows.get(key, {})
            output_rows.append(
                {
                    **row,
                    **{
                        name: value
                        for name, value in features.items()
                        if name not in {"symbol", "timeframe", "decision_time"}
                    },
                    "window": window.name,
                }
            )
    return output_rows


def _accepted_rows_for_window(
    window: TimeframeWindowConfig,
    replay_report: dict[str, object],
    symbols: list[str],
) -> list[dict[str, object]]:
    accepted_rows: list[dict[str, object]] = []
    symbol_set = set(symbols)
    for replay in replay_report["replays"]:
        replay_item = dict(replay)
        selected_rows = [
            dict(row)
            for row in pq.read_table(
                window.replay_report_path.parent / str(replay_item["trades_path"])
            ).to_pylist()
        ]
        selected_rows = [
            row
            for row in selected_rows
            if str(row["symbol"]) in symbol_set
            and row.get("realized_r_after_costs") is not None
            and row.get("exit_time") is not None
        ]
        backtest_report = evaluate_signal_strategy(
            f"{window.name}_timeframe_scan",
            [_signal(row) for row in selected_rows],
            _backtest_config(_pack_risk_controls(Path(str(replay_item["pack_manifest_path"])))),
        )
        accepted_keys = {
            (trade.decision_time.astimezone(UTC), trade.symbol) for trade in backtest_report.trades
        }
        selected_by_key = {
            (_as_datetime(row["decision_time"]), str(row["symbol"])): row for row in selected_rows
        }
        accepted_rows.extend(
            selected_by_key[key] for key in accepted_keys if key in selected_by_key
        )
    return sorted(
        accepted_rows,
        key=lambda row: (
            _as_datetime(row["decision_time"]),
            int(row.get("rank", 0)),
            row["symbol"],
        ),
    )


def _feature_rows_for_keys(
    rows_path: Path,
    columns: list[str],
    wanted_keys: set[tuple[str, str, datetime]],
    symbols: list[str],
) -> dict[tuple[str, str, datetime], dict[str, object]]:
    min_time = min(key[2] for key in wanted_keys)
    max_time = max(key[2] for key in wanted_keys)
    rows = pq.read_table(
        rows_path,
        columns=columns,
        filters=[
            ("symbol", "in", symbols),
            ("decision_time", ">=", min_time),
            ("decision_time", "<=", max_time),
        ],
    ).to_pylist()
    return {
        (str(row["symbol"]), str(row["timeframe"]), _as_datetime(row["decision_time"])): dict(row)
        for row in rows
        if (str(row["symbol"]), str(row["timeframe"]), _as_datetime(row["decision_time"]))
        in wanted_keys
    }


def _scenario_report(
    config: TimeframeContinuationScanConfig,
    scenario: TimeframeScenario,
    base_rows: list[dict[str, object]],
) -> dict[str, object]:
    rows = [
        row
        for row in _daily_capped_rows(base_rows, scenario)
        if _scenario_row_passes(row, scenario)
    ]
    net_rs = [float(row["realized_r_after_costs"]) for row in rows]
    stop_touch = [float(row["max_adverse_excursion_r"]) <= -1.0 for row in rows]
    clean_runners = [
        float(row["max_favorable_excursion_r"]) >= config.target_runner_r
        and float(row["max_adverse_excursion_r"]) > -1.0
        for row in rows
    ]
    return {
        "name": scenario.name,
        "description": scenario.description,
        "max_trades_per_day": scenario.max_trades_per_day,
        "allowed_symbols": list(scenario.allowed_symbols),
        "feature_filters": [
            {
                "feature": item.feature,
                "operator": item.operator,
                "value": item.value,
            }
            for item in scenario.feature_filters
        ],
        "accepted_trade_count": len(rows),
        "average_r": _mean(net_rs),
        "win_rate": _share([value > 0 for value in net_rs]),
        "profit_factor": _profit_factor(net_rs),
        "stop_touch_share": _share(stop_touch),
        "clean_runner_share": _share(clean_runners),
        "clean_runner_count": sum(clean_runners),
        "windows": _group_rows(rows, "window"),
        "symbols": _group_rows(rows, "symbol"),
    }


def _daily_capped_rows(
    rows: list[dict[str, object]],
    scenario: TimeframeScenario,
) -> list[dict[str, object]]:
    day_counts: dict[str, int] = defaultdict(int)
    output = []
    allowed_symbols = set(scenario.allowed_symbols)
    for row in sorted(
        rows,
        key=lambda item: (
            _as_datetime(item["decision_time"]),
            int(item.get("rank", 0)),
            str(item["symbol"]),
        ),
    ):
        if str(row["symbol"]) not in allowed_symbols:
            continue
        day_key = _day_key(_as_datetime(row["decision_time"]))
        if (
            scenario.max_trades_per_day is not None
            and day_counts[day_key] >= scenario.max_trades_per_day
        ):
            continue
        day_counts[day_key] += 1
        output.append(row)
    return output


def _scenario_row_passes(row: dict[str, object], scenario: TimeframeScenario) -> bool:
    return all(_filter_passes(row, item) for item in scenario.feature_filters)


def _filter_passes(row: dict[str, object], item: FeatureFilter) -> bool:
    raw_value = row.get(item.feature)
    if raw_value is None:
        return False
    value = float(raw_value)
    if item.operator == "<=":
        return value <= item.value
    if item.operator == ">=":
        return value >= item.value
    if item.operator == "<":
        return value < item.value
    if item.operator == ">":
        return value > item.value
    if item.operator in {"==", "="}:
        return value == item.value
    raise ValueError(f"unsupported filter operator: {item.operator}")


def _group_rows(rows: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    return [
        {
            "name": name,
            "trade_count": len(group),
            "average_r": _mean([float(row["realized_r_after_costs"]) for row in group]),
        }
        for name, group in sorted(groups.items())
    ]


def _decision(scenarios: list[dict[str, object]]) -> dict[str, object]:
    baseline = next((row for row in scenarios if row["name"] == "core3_base"), None)
    baseline_average_r = float(dict(baseline).get("average_r", 0.0)) if baseline else 0.0
    improved = [
        row
        for row in scenarios
        if row["name"] != "core3_base"
        and int(row["accepted_trade_count"]) >= 100
        and float(row["average_r"]) > baseline_average_r
        and float(row["clean_runner_share"]) >= 0.15
    ]
    best = max(scenarios, key=lambda row: float(row["average_r"])) if scenarios else None
    return {
        "research_only": True,
        "live_trading_approved": False,
        "working_model": False,
        "higher_timeframe_filter_passed": bool(improved),
        "best_average_r_scenario": best["name"] if best else None,
        "notes": (
            "Higher-timeframe confirmation over the current 1m entry stream must improve "
            "average R and runner share with at least 100 trades to justify further promotion."
        ),
    }


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        f"Target clean runner: `{float(payload['target_runner_r']):.1f}R`",
        "",
        "| scenario | trades | avg R | win rate | PF | stop touch | clean runners |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        lines.append(
            "| "
            f"`{item['name']}` | "
            f"{int(item['accepted_trade_count'])} | "
            f"{float(item['average_r']):.4f} | "
            f"{float(item['win_rate']):.2%} | "
            f"{float(item['profit_factor']):.3f} | "
            f"{float(item['stop_touch_share']):.2%} | "
            f"{float(item['clean_runner_share']):.2%} |"
        )
    lines.extend(["", "## Decision", ""])
    decision = dict(payload["decision"])
    lines.extend(
        [
            f"- Research only: `{decision['research_only']}`",
            f"- Live trading approved: `{decision['live_trading_approved']}`",
            f"- Working model: `{decision['working_model']}`",
            f"- Higher-timeframe filter passed: `{decision['higher_timeframe_filter_passed']}`",
            f"- Best average-R scenario: `{decision['best_average_r_scenario']}`",
            "",
            "Backtest/filter diagnostics do not approve live trading.",
            "",
        ]
    )
    return "\n".join(lines)


def _signal(row: dict[str, object]) -> SignalRow:
    return SignalRow(
        decision_time=_as_datetime(row["decision_time"]),
        symbol=str(row["symbol"]),
        timeframe=str(row["timeframe"]),
        side="long",
        gross_r=float(row["realized_r_after_costs"]),
        confidence=_expected_r_confidence(float(row["expected_r"])),
        exit_time=_as_datetime(row["exit_time"]),
    )


def _pack_risk_controls(pack_manifest_path: Path) -> dict[str, object]:
    pack = _read_json(pack_manifest_path)
    strategy = dict(pack["strategy"])
    return dict(strategy.get("risk_controls", {}))


def _backtest_config(risk_controls: dict[str, object]) -> BacktestConfig:
    return BacktestConfig(
        initial_equity=10000,
        risk_per_trade_pct=0.01,
        max_trades_per_symbol=_optional_int(risk_controls.get("max_trades_per_symbol")),
        max_trades_per_decision_time=_optional_int(
            risk_controls.get("max_trades_per_decision_time")
        ),
        loss_cooldown_signals=int(risk_controls.get("loss_cooldown_signals", 0)),
    )


def _expected_r_confidence(expected_r: float) -> float:
    return min(1.0, max(0.01, expected_r))


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    return wins / losses if losses else float("inf")


def _share(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 0.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(path)
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _day_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    payload = build_timeframe_continuation_scan_report(
        TimeframeContinuationScanConfig.from_path(args.config)
    )
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        print(
            f"name={item['name']} "
            f"trades={int(item['accepted_trade_count'])} "
            f"avg_r={float(item['average_r']):.4f} "
            f"clean_runners={float(item['clean_runner_share']):.2%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
