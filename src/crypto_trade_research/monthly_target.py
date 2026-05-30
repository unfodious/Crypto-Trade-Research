"""Evaluate CT-180 style trades against high monthly return targets."""

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

SCHEMA_VERSION = "research.monthly-target.v1"


@dataclass(frozen=True, slots=True)
class MonthlyTargetWindowConfig:
    name: str
    replay_report_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MonthlyTargetWindowConfig:
        return cls(
            name=str(payload["name"]),
            replay_report_path=Path(str(payload["replay_report_path"])),
        )


@dataclass(frozen=True, slots=True)
class MonthlyTargetScenario:
    name: str
    description: str
    risk_per_trade_pct: float
    max_trades_per_day: int | None = None
    allowed_symbols: tuple[str, ...] = ()
    max_rank: int | None = None
    min_expected_r: float | None = None
    min_probability: float | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MonthlyTargetScenario:
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            risk_per_trade_pct=float(payload["risk_per_trade_pct"]),
            max_trades_per_day=_optional_int(payload.get("max_trades_per_day")),
            allowed_symbols=tuple(str(item) for item in payload.get("allowed_symbols", [])),
            max_rank=_optional_int(payload.get("max_rank")),
            min_expected_r=_optional_float(payload.get("min_expected_r")),
            min_probability=_optional_float(payload.get("min_probability")),
        )


@dataclass(frozen=True, slots=True)
class MonthlyTargetConfig:
    report_name: str
    issue_id: str
    epic_id: str
    initial_equity: float
    target_monthly_return_pct: float
    max_drawdown_gate_pct: float
    output_json_path: Path
    output_markdown_path: Path
    windows: tuple[MonthlyTargetWindowConfig, ...]
    scenarios: tuple[MonthlyTargetScenario, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MonthlyTargetConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            initial_equity=float(payload.get("initial_equity", 1000.0)),
            target_monthly_return_pct=float(payload.get("target_monthly_return_pct", 0.30)),
            max_drawdown_gate_pct=float(payload.get("max_drawdown_gate_pct", 0.08)),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            windows=tuple(
                MonthlyTargetWindowConfig.from_dict(dict(item)) for item in payload["windows"]
            ),
            scenarios=tuple(
                MonthlyTargetScenario.from_dict(dict(item)) for item in payload["scenarios"]
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> MonthlyTargetConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class Trade:
    decision_time: datetime
    exit_time: datetime
    symbol: str
    timeframe: str
    net_r: float
    window: str


@dataclass(slots=True)
class OpenPosition:
    exit_time: datetime
    symbol: str
    window: str
    net_r: float
    pnl: float


@dataclass(slots=True)
class SimulationState:
    equity: float
    peak_equity: float
    max_drawdown_pct: float = 0.0

    @property
    def current_drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - self.equity) / self.peak_equity


def build_monthly_target_report(config: MonthlyTargetConfig) -> dict[str, object]:
    """Build a monthly-return target matrix from replay selected trades."""

    if config.initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if config.target_monthly_return_pct <= 0:
        raise ValueError("target_monthly_return_pct must be positive")
    if config.max_drawdown_gate_pct <= 0:
        raise ValueError("max_drawdown_gate_pct must be positive")
    if not config.scenarios:
        raise ValueError("scenarios must not be empty")

    scenarios = []
    for scenario in config.scenarios:
        _validate_scenario(scenario)
        trades = _load_scenario_trades(config.windows, scenario)
        aggregate = _simulate(config.initial_equity, scenario, trades, config)
        window_replays = [
            _simulate(
                config.initial_equity,
                scenario,
                [trade for trade in trades if trade.window == window.name],
                config,
            )
            | {"window": window.name}
            for window in config.windows
        ]
        scenarios.append(
            {
                **aggregate,
                "window_replays": window_replays,
                "passes_drawdown_gate": aggregate["max_drawdown_pct"]
                <= config.max_drawdown_gate_pct,
                "passes_monthly_target": aggregate["geometric_average_monthly_return_pct"]
                >= config.target_monthly_return_pct,
                "passes_window_positive": all(
                    float(row["total_return_pct"]) > 0 and int(row["accepted_trade_count"]) >= 50
                    for row in window_replays
                ),
                "passes_trade_floor": int(aggregate["accepted_trade_count"]) >= 100,
            }
        )

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "initial_equity": config.initial_equity,
        "target_monthly_return_pct": config.target_monthly_return_pct,
        "max_drawdown_gate_pct": config.max_drawdown_gate_pct,
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


def _load_scenario_trades(
    windows: tuple[MonthlyTargetWindowConfig, ...],
    scenario: MonthlyTargetScenario,
) -> list[Trade]:
    trades: list[Trade] = []
    for window in windows:
        replay_report = _read_json(window.replay_report_path)
        for replay in replay_report["replays"]:
            replay_item = dict(replay)
            selected_rows = pq.read_table(
                window.replay_report_path.parent / str(replay_item["trades_path"])
            ).to_pylist()
            filtered_rows = [
                dict(row)
                for row in selected_rows
                if _scenario_row_passes(dict(row), scenario)
                and row.get("realized_r_after_costs") is not None
                and row.get("exit_time") is not None
            ]
            pack_manifest_path = Path(str(replay_item["pack_manifest_path"]))
            risk_controls = _pack_risk_controls(pack_manifest_path)
            backtest_report = evaluate_signal_strategy(
                f"{scenario.name}_{window.name}",
                [_signal(row) for row in filtered_rows],
                _backtest_config(risk_controls),
            )
            trades.extend(
                Trade(
                    decision_time=trade.decision_time.astimezone(UTC),
                    exit_time=trade.exit_time.astimezone(UTC),
                    symbol=trade.symbol,
                    timeframe=trade.timeframe,
                    net_r=trade.net_r,
                    window=window.name,
                )
                for trade in backtest_report.trades
            )
    return sorted(trades, key=lambda trade: (trade.decision_time, trade.symbol))


def _scenario_row_passes(row: dict[str, object], scenario: MonthlyTargetScenario) -> bool:
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


def _simulate(
    initial_equity: float,
    scenario: MonthlyTargetScenario,
    trades: list[Trade],
    config: MonthlyTargetConfig,
) -> dict[str, object]:
    state = SimulationState(equity=initial_equity, peak_equity=initial_equity)
    open_positions: list[OpenPosition] = []
    day_counts: dict[str, int] = defaultdict(int)
    monthly: dict[str, dict[str, object]] = {}
    symbols: dict[str, dict[str, object]] = {}
    skipped_trade_count = 0
    accepted_trade_count = 0

    for trade in trades:
        _settle_positions(state, open_positions, trade.decision_time, monthly, symbols)
        if _day_cap_reached(scenario, trade, day_counts):
            skipped_trade_count += 1
            continue
        day_counts[_day_key(trade.decision_time)] += 1
        pnl = state.equity * scenario.risk_per_trade_pct * trade.net_r
        open_positions.append(
            OpenPosition(
                exit_time=trade.exit_time,
                symbol=trade.symbol,
                window=trade.window,
                net_r=trade.net_r,
                pnl=pnl,
            )
        )
        accepted_trade_count += 1

    _settle_positions(state, open_positions, datetime.max.replace(tzinfo=UTC), monthly, symbols)
    monthly_rows = [
        {"month": month, **_finalize_group(row)} for month, row in sorted(monthly.items())
    ]
    symbol_rows = [_finalize_named_group(symbol, row) for symbol, row in sorted(symbols.items())]
    target_hits = [
        row for row in monthly_rows if float(row["return_pct"]) >= config.target_monthly_return_pct
    ]
    positive_months = [row for row in monthly_rows if float(row["return_pct"]) > 0]
    return {
        "name": scenario.name,
        "description": scenario.description,
        "risk_per_trade_pct": scenario.risk_per_trade_pct,
        "max_trades_per_day": scenario.max_trades_per_day,
        "allowed_symbols": list(scenario.allowed_symbols),
        "max_rank": scenario.max_rank,
        "min_expected_r": scenario.min_expected_r,
        "min_probability": scenario.min_probability,
        "initial_equity": initial_equity,
        "final_equity": state.equity,
        "total_pnl": state.equity - initial_equity,
        "total_return_pct": (state.equity / initial_equity) - 1,
        "max_drawdown_pct": state.max_drawdown_pct,
        "accepted_trade_count": accepted_trade_count,
        "skipped_trade_count": skipped_trade_count,
        "month_count": len(monthly_rows),
        "geometric_average_monthly_return_pct": _geometric_average_monthly_return(monthly_rows),
        "arithmetic_average_monthly_return_pct": _mean(
            [float(row["return_pct"]) for row in monthly_rows]
        ),
        "target_month_hit_rate": len(target_hits) / len(monthly_rows) if monthly_rows else 0.0,
        "positive_month_rate": len(positive_months) / len(monthly_rows) if monthly_rows else 0.0,
        "best_month": max(monthly_rows, key=lambda row: float(row["return_pct"]))
        if monthly_rows
        else None,
        "worst_month": min(monthly_rows, key=lambda row: float(row["return_pct"]))
        if monthly_rows
        else None,
        "monthly": monthly_rows,
        "symbols": symbol_rows,
    }


def _day_cap_reached(
    scenario: MonthlyTargetScenario,
    trade: Trade,
    day_counts: dict[str, int],
) -> bool:
    return (
        scenario.max_trades_per_day is not None
        and day_counts[_day_key(trade.decision_time)] >= scenario.max_trades_per_day
    )


def _settle_positions(
    state: SimulationState,
    open_positions: list[OpenPosition],
    until: datetime,
    monthly: dict[str, dict[str, object]],
    symbols: dict[str, dict[str, object]],
) -> None:
    still_open: list[OpenPosition] = []
    for position in open_positions:
        if position.exit_time > until:
            still_open.append(position)
            continue
        previous_equity = state.equity
        state.equity += position.pnl
        state.peak_equity = max(state.peak_equity, state.equity)
        state.max_drawdown_pct = max(state.max_drawdown_pct, state.current_drawdown_pct)
        _record_trade(
            monthly,
            _month_key(position.exit_time),
            previous_equity,
            state.equity,
            position,
        )
        _record_trade(symbols, position.symbol, previous_equity, state.equity, position)
    open_positions[:] = still_open


def _record_trade(
    groups: dict[str, dict[str, object]],
    key: str,
    previous_equity: float,
    current_equity: float,
    position: OpenPosition,
) -> None:
    row = groups.setdefault(
        key,
        {
            "start_equity": previous_equity,
            "end_equity": previous_equity,
            "pnl": 0.0,
            "accepted_trade_count": 0,
            "r_sum": 0.0,
            "wins": 0,
            "gross_win_r": 0.0,
            "gross_loss_r": 0.0,
        },
    )
    row["end_equity"] = current_equity
    row["pnl"] = float(row["pnl"]) + position.pnl
    row["accepted_trade_count"] = int(row["accepted_trade_count"]) + 1
    row["r_sum"] = float(row["r_sum"]) + position.net_r
    if position.net_r > 0:
        row["wins"] = int(row["wins"]) + 1
        row["gross_win_r"] = float(row["gross_win_r"]) + position.net_r
    elif position.net_r < 0:
        row["gross_loss_r"] = float(row["gross_loss_r"]) + abs(position.net_r)


def _finalize_named_group(name: str, row: dict[str, object]) -> dict[str, object]:
    return {"name": name, **_finalize_group(row)}


def _finalize_group(row: dict[str, object]) -> dict[str, object]:
    accepted = int(row["accepted_trade_count"])
    start_equity = float(row["start_equity"])
    end_equity = float(row["end_equity"])
    gross_loss_r = float(row["gross_loss_r"])
    return {
        "start_equity": start_equity,
        "end_equity": end_equity,
        "pnl": float(row["pnl"]),
        "return_pct": (end_equity / start_equity) - 1 if start_equity else 0.0,
        "accepted_trade_count": accepted,
        "average_r": float(row["r_sum"]) / accepted if accepted else 0.0,
        "win_rate": int(row["wins"]) / accepted if accepted else 0.0,
        "profit_factor": float(row["gross_win_r"]) / gross_loss_r if gross_loss_r else float("inf"),
    }


def _geometric_average_monthly_return(monthly_rows: list[dict[str, object]]) -> float:
    if not monthly_rows:
        return 0.0
    product = 1.0
    for row in monthly_rows:
        product *= 1 + float(row["return_pct"])
    if product <= 0:
        return -1.0
    return product ** (1 / len(monthly_rows)) - 1


def _decision(scenarios: list[dict[str, object]]) -> dict[str, object]:
    viable = [
        scenario
        for scenario in scenarios
        if bool(scenario["passes_monthly_target"])
        and bool(scenario["passes_drawdown_gate"])
        and bool(scenario["passes_trade_floor"])
        and bool(scenario["passes_window_positive"])
    ]
    best = max(
        scenarios,
        key=lambda row: (
            float(row["geometric_average_monthly_return_pct"]),
            -float(row["max_drawdown_pct"]),
        ),
    )
    return {
        "research_only": True,
        "live_trading_approved": False,
        "working_model": False,
        "best_viable_scenario": viable[0]["name"] if viable else None,
        "best_return_scenario": best["name"] if scenarios else None,
        "notes": (
            "Monthly target evidence only. A high-return row is not acceptable if it buys "
            "the return with excessive drawdown or tiny sample size."
        ),
    }


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        f"Target monthly return: `{float(payload['target_monthly_return_pct']):.2%}`",
        f"Max drawdown gate: `{float(payload['max_drawdown_gate_pct']):.2%}`",
        "",
        "| scenario | risk/trade | final equity | total return | geom month | "
        "best month | worst month | target months | max DD | trades | gates |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        best = dict(item["best_month"]) if item.get("best_month") else {}
        worst = dict(item["worst_month"]) if item.get("worst_month") else {}
        gates = _gate_summary(item)
        lines.append(
            "| "
            f"`{item['name']}` | "
            f"{float(item['risk_per_trade_pct']):.2%} | "
            f"${float(item['final_equity']):,.2f} | "
            f"{float(item['total_return_pct']):.2%} | "
            f"{float(item['geometric_average_monthly_return_pct']):.2%} | "
            f"{float(best.get('return_pct', 0.0)):.2%} | "
            f"{float(worst.get('return_pct', 0.0)):.2%} | "
            f"{float(item['target_month_hit_rate']):.0%} | "
            f"{float(item['max_drawdown_pct']):.2%} | "
            f"{int(item['accepted_trade_count'])} | "
            f"{gates} |"
        )

    lines.extend(["", "## Scenario Details", ""])
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        lines.extend(
            [
                f"### {item['name']}",
                "",
                f"- Description: {item['description']}",
                f"- Symbols: `{', '.join(item['allowed_symbols']) or 'all selected'}`",
                f"- Max rank: `{item['max_rank']}`",
                f"- Min expected R: `{item['min_expected_r']}`",
                f"- Min probability: `{item['min_probability']}`",
                "",
                "| month | trades | return | end equity | avg R | profit factor |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for month in item["monthly"]:
            month_item = dict(month)
            lines.append(
                "| "
                f"{month_item['month']} | "
                f"{int(month_item['accepted_trade_count'])} | "
                f"{float(month_item['return_pct']):.2%} | "
                f"${float(month_item['end_equity']):,.2f} | "
                f"{float(month_item['average_r']):.4f} | "
                f"{float(month_item['profit_factor']):.3f} |"
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
            f"- Best viable scenario: `{decision['best_viable_scenario']}`",
            f"- Best return scenario: `{decision['best_return_scenario']}`",
            "",
            "Backtest evidence does not approve live trading.",
            "",
        ]
    )
    return "\n".join(lines)


def _gate_summary(item: dict[str, object]) -> str:
    gates = []
    gates.append("month" if item["passes_monthly_target"] else "no-month")
    gates.append("dd" if item["passes_drawdown_gate"] else "no-dd")
    gates.append("n" if item["passes_trade_floor"] else "no-n")
    gates.append("window" if item["passes_window_positive"] else "no-window")
    return ",".join(gates)


def _expected_r_confidence(expected_r: float) -> float:
    return min(1.0, max(0.01, expected_r))


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(path)
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _validate_scenario(scenario: MonthlyTargetScenario) -> None:
    if scenario.risk_per_trade_pct <= 0:
        raise ValueError("risk_per_trade_pct must be positive")
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


def _month_key(value: datetime) -> str:
    return value.strftime("%Y-%m")


def _day_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    payload = build_monthly_target_report(MonthlyTargetConfig.from_path(args.config))
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        print(
            f"name={item['name']} "
            f"risk={float(item['risk_per_trade_pct']):.2%} "
            f"final=${float(item['final_equity']):.2f} "
            f"geom_month={float(item['geometric_average_monthly_return_pct']):.2%} "
            f"max_dd={float(item['max_drawdown_pct']):.2%} "
            f"trades={int(item['accepted_trade_count'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
