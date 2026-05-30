"""Diagnose whether selected trades contain enough runner payoff potential."""

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

SCHEMA_VERSION = "research.payoff-diagnostics.v1"


@dataclass(frozen=True, slots=True)
class PayoffWindowConfig:
    name: str
    replay_report_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PayoffWindowConfig:
        return cls(
            name=str(payload["name"]),
            replay_report_path=Path(str(payload["replay_report_path"])),
        )


@dataclass(frozen=True, slots=True)
class PayoffScenario:
    name: str
    description: str
    max_trades_per_day: int | None = None
    allowed_symbols: tuple[str, ...] = ()
    max_rank: int | None = None
    min_expected_r: float | None = None
    min_probability: float | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PayoffScenario:
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            max_trades_per_day=_optional_int(payload.get("max_trades_per_day")),
            allowed_symbols=tuple(str(item) for item in payload.get("allowed_symbols", [])),
            max_rank=_optional_int(payload.get("max_rank")),
            min_expected_r=_optional_float(payload.get("min_expected_r")),
            min_probability=_optional_float(payload.get("min_probability")),
        )


@dataclass(frozen=True, slots=True)
class PayoffDiagnosticsConfig:
    report_name: str
    issue_id: str
    epic_id: str
    output_json_path: Path
    output_markdown_path: Path
    runner_thresholds_r: tuple[float, ...]
    target_runner_r: float
    min_clean_runner_share: float
    windows: tuple[PayoffWindowConfig, ...]
    scenarios: tuple[PayoffScenario, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PayoffDiagnosticsConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            runner_thresholds_r=tuple(float(item) for item in payload["runner_thresholds_r"]),
            target_runner_r=float(payload.get("target_runner_r", 3.0)),
            min_clean_runner_share=float(payload.get("min_clean_runner_share", 0.20)),
            windows=tuple(PayoffWindowConfig.from_dict(dict(item)) for item in payload["windows"]),
            scenarios=tuple(PayoffScenario.from_dict(dict(item)) for item in payload["scenarios"]),
        )

    @classmethod
    def from_path(cls, path: Path) -> PayoffDiagnosticsConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_payoff_diagnostics_report(config: PayoffDiagnosticsConfig) -> dict[str, object]:
    """Build runner-potential diagnostics from replay selected trades."""

    if not config.runner_thresholds_r:
        raise ValueError("runner_thresholds_r must not be empty")
    if config.target_runner_r <= 0:
        raise ValueError("target_runner_r must be positive")
    if not 0 < config.min_clean_runner_share <= 1:
        raise ValueError("min_clean_runner_share must be in (0, 1]")
    if not config.scenarios:
        raise ValueError("scenarios must not be empty")

    scenarios = []
    for scenario in config.scenarios:
        _validate_scenario(scenario)
        rows = _load_accepted_rows(config.windows, scenario)
        scenarios.append(_scenario_report(config, scenario, rows))

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "runner_thresholds_r": list(config.runner_thresholds_r),
        "target_runner_r": config.target_runner_r,
        "min_clean_runner_share": config.min_clean_runner_share,
        "windows": [
            {"name": window.name, "replay_report_path": str(window.replay_report_path)}
            for window in config.windows
        ],
        "scenarios": scenarios,
        "decision": _decision(config, scenarios),
    }
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _load_accepted_rows(
    windows: tuple[PayoffWindowConfig, ...],
    scenario: PayoffScenario,
) -> list[dict[str, object]]:
    accepted_rows: list[dict[str, object]] = []
    for window in windows:
        replay_report = _read_json(window.replay_report_path)
        for replay in replay_report["replays"]:
            replay_item = dict(replay)
            selected_rows = [
                dict(row)
                for row in pq.read_table(
                    window.replay_report_path.parent / str(replay_item["trades_path"])
                ).to_pylist()
            ]
            filtered_rows = [
                row
                for row in selected_rows
                if _scenario_row_passes(row, scenario)
                and row.get("realized_r_after_costs") is not None
                and row.get("exit_time") is not None
            ]
            backtest_report = evaluate_signal_strategy(
                f"{scenario.name}_{window.name}",
                [_signal(row) for row in filtered_rows],
                _backtest_config(_pack_risk_controls(Path(str(replay_item["pack_manifest_path"])))),
            )
            accepted_keys = {
                (trade.decision_time.astimezone(UTC), trade.symbol)
                for trade in backtest_report.trades
            }
            rows_by_key = {
                (_as_datetime(row["decision_time"]), str(row["symbol"])): row
                for row in filtered_rows
            }
            for key in accepted_keys:
                row = rows_by_key.get(key)
                if row is not None:
                    accepted_rows.append({**row, "window": window.name})

    capped_rows: list[dict[str, object]] = []
    day_counts: dict[str, int] = defaultdict(int)
    for row in sorted(
        accepted_rows,
        key=lambda item: (
            _as_datetime(item["decision_time"]),
            int(item.get("rank", 0)),
            str(item["symbol"]),
        ),
    ):
        day_key = _day_key(_as_datetime(row["decision_time"]))
        if (
            scenario.max_trades_per_day is not None
            and day_counts[day_key] >= scenario.max_trades_per_day
        ):
            continue
        day_counts[day_key] += 1
        capped_rows.append(row)
    return capped_rows


def _scenario_row_passes(row: dict[str, object], scenario: PayoffScenario) -> bool:
    if scenario.allowed_symbols and str(row["symbol"]) not in scenario.allowed_symbols:
        return False
    if scenario.max_rank is not None and int(row["rank"]) > scenario.max_rank:
        return False
    if scenario.min_expected_r is not None and float(row["expected_r"]) < scenario.min_expected_r:
        return False
    return not (
        scenario.min_probability is not None
        and float(row["target_before_stop_probability"]) < scenario.min_probability
    )


def _scenario_report(
    config: PayoffDiagnosticsConfig,
    scenario: PayoffScenario,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    net_rs = [float(row["realized_r_after_costs"]) for row in rows]
    mfe = [float(row["max_favorable_excursion_r"]) for row in rows]
    mae = [float(row["max_adverse_excursion_r"]) for row in rows]
    thresholds = [
        _threshold_report(threshold, mfe, mae) for threshold in sorted(config.runner_thresholds_r)
    ]
    target_row = next(
        row for row in thresholds if float(row["threshold_r"]) == config.target_runner_r
    )
    return {
        "name": scenario.name,
        "description": scenario.description,
        "max_trades_per_day": scenario.max_trades_per_day,
        "allowed_symbols": list(scenario.allowed_symbols),
        "max_rank": scenario.max_rank,
        "min_expected_r": scenario.min_expected_r,
        "min_probability": scenario.min_probability,
        "accepted_trade_count": len(rows),
        "average_r": _mean(net_rs),
        "win_rate": _share([value > 0 for value in net_rs]),
        "profit_factor": _profit_factor(net_rs),
        "stop_touch_share": _share([value <= -1.0 for value in mae]),
        "target_runner_clean_share": target_row["clean_runner_share"],
        "passes_runner_floor": float(target_row["clean_runner_share"])
        >= config.min_clean_runner_share,
        "thresholds": thresholds,
        "symbols": _group_rows(rows, "symbol"),
        "windows": _group_rows(rows, "window"),
    }


def _threshold_report(
    threshold: float,
    mfe: list[float],
    mae: list[float],
) -> dict[str, object]:
    count = len(mfe)
    runner = [value >= threshold for value in mfe]
    clean = [
        favorable >= threshold and adverse > -1.0
        for favorable, adverse in zip(mfe, mae, strict=True)
    ]
    return {
        "threshold_r": threshold,
        "runner_count": sum(runner),
        "runner_share": _share(runner),
        "clean_runner_count": sum(clean),
        "clean_runner_share": sum(clean) / count if count else 0.0,
    }


def _group_rows(rows: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    output = []
    for name, group in sorted(groups.items()):
        net_rs = [float(row["realized_r_after_costs"]) for row in group]
        output.append(
            {
                "name": name,
                "trade_count": len(group),
                "average_r": _mean(net_rs),
                "win_rate": _share([value > 0 for value in net_rs]),
            }
        )
    return output


def _decision(
    config: PayoffDiagnosticsConfig,
    scenarios: list[dict[str, object]],
) -> dict[str, object]:
    passing = [scenario for scenario in scenarios if bool(scenario["passes_runner_floor"])]
    return {
        "research_only": True,
        "live_trading_approved": False,
        "working_model": False,
        "runner_floor_passed": bool(passing),
        "best_runner_scenario": max(
            scenarios,
            key=lambda item: float(item["target_runner_clean_share"]),
        )["name"]
        if scenarios
        else None,
        "notes": (
            f"Target runner floor requires at least {config.min_clean_runner_share:.0%} "
            f"clean >= {config.target_runner_r:.1f}R runners."
        ),
    }


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        f"Target runner: `{float(payload['target_runner_r']):.1f}R`",
        f"Clean runner floor: `{float(payload['min_clean_runner_share']):.0%}`",
        "",
        "| scenario | trades | avg R | win rate | stop touch | clean target runners | decision |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        lines.append(
            "| "
            f"`{item['name']}` | "
            f"{int(item['accepted_trade_count'])} | "
            f"{float(item['average_r']):.4f} | "
            f"{float(item['win_rate']):.2%} | "
            f"{float(item['stop_touch_share']):.2%} | "
            f"{float(item['target_runner_clean_share']):.2%} | "
            f"{'pass' if item['passes_runner_floor'] else 'reject'} |"
        )

    lines.extend(["", "## Runner Thresholds", ""])
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        lines.extend(
            [
                f"### {item['name']}",
                "",
                "| threshold | runners | runner share | clean runners | clean share |",
                "| ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for threshold in item["thresholds"]:
            row = dict(threshold)
            lines.append(
                "| "
                f"{float(row['threshold_r']):.1f}R | "
                f"{int(row['runner_count'])} | "
                f"{float(row['runner_share']):.2%} | "
                f"{int(row['clean_runner_count'])} | "
                f"{float(row['clean_runner_share']):.2%} |"
            )
        lines.append("")

    decision = dict(payload["decision"])
    lines.extend(
        [
            "## Decision",
            "",
            f"- Research only: `{decision['research_only']}`",
            f"- Live trading approved: `{decision['live_trading_approved']}`",
            f"- Working model: `{decision['working_model']}`",
            f"- Runner floor passed: `{decision['runner_floor_passed']}`",
            f"- Best runner scenario: `{decision['best_runner_scenario']}`",
            "",
            "Backtest/path diagnostics do not approve live trading.",
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


def _validate_scenario(scenario: PayoffScenario) -> None:
    if scenario.max_trades_per_day is not None and scenario.max_trades_per_day <= 0:
        raise ValueError("max_trades_per_day must be positive when set")
    if scenario.max_rank is not None and scenario.max_rank <= 0:
        raise ValueError("max_rank must be positive when set")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


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
    payload = build_payoff_diagnostics_report(PayoffDiagnosticsConfig.from_path(args.config))
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        print(
            f"name={item['name']} "
            f"trades={int(item['accepted_trade_count'])} "
            f"avg_r={float(item['average_r']):.4f} "
            f"clean_target_runners={float(item['target_runner_clean_share']):.2%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
