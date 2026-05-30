"""Evaluate accepted historical trades under adaptive sizing policies."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

SCHEMA_VERSION = "research.adaptive-sizing.v1"


@dataclass(frozen=True, slots=True)
class ReplayWindowConfig:
    name: str
    replay_report_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReplayWindowConfig:
        return cls(
            name=str(payload["name"]),
            replay_report_path=Path(str(payload["replay_report_path"])),
        )


@dataclass(frozen=True, slots=True)
class DrawdownRiskStep:
    at_drawdown_pct: float
    risk_per_trade_pct: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DrawdownRiskStep:
        return cls(
            at_drawdown_pct=float(payload["at_drawdown_pct"]),
            risk_per_trade_pct=float(payload["risk_per_trade_pct"]),
        )


@dataclass(frozen=True, slots=True)
class AdaptiveSizingScenario:
    name: str
    description: str
    base_risk_per_trade_pct: float
    drawdown_risk_steps: tuple[DrawdownRiskStep, ...] = ()
    max_trades_per_day: int | None = None
    allowed_symbols: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AdaptiveSizingScenario:
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            base_risk_per_trade_pct=float(payload["base_risk_per_trade_pct"]),
            drawdown_risk_steps=tuple(
                DrawdownRiskStep.from_dict(dict(item))
                for item in payload.get("drawdown_risk_steps", [])
            ),
            max_trades_per_day=_optional_int(payload.get("max_trades_per_day")),
            allowed_symbols=tuple(str(item) for item in payload.get("allowed_symbols", [])),
        )


@dataclass(frozen=True, slots=True)
class AdaptiveSizingConfig:
    report_name: str
    issue_id: str
    epic_id: str
    initial_equity: float
    max_drawdown_gate_pct: float
    output_json_path: Path
    output_markdown_path: Path
    windows: tuple[ReplayWindowConfig, ...]
    scenarios: tuple[AdaptiveSizingScenario, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AdaptiveSizingConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            initial_equity=float(payload.get("initial_equity", 1000.0)),
            max_drawdown_gate_pct=float(payload.get("max_drawdown_gate_pct", 0.08)),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            windows=tuple(ReplayWindowConfig.from_dict(dict(item)) for item in payload["windows"]),
            scenarios=tuple(
                AdaptiveSizingScenario.from_dict(dict(item)) for item in payload["scenarios"]
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> AdaptiveSizingConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class Trade:
    decision_time: datetime
    exit_time: datetime
    symbol: str
    side: str
    net_r: float
    window: str

    @classmethod
    def from_row(cls, row: dict[str, object], window: str) -> Trade:
        return cls(
            decision_time=_as_datetime(row["decision_time"]),
            exit_time=_as_datetime(row["exit_time"]),
            symbol=str(row["symbol"]),
            side=str(row.get("side", "")),
            net_r=float(row["net_r"]),
            window=window,
        )


@dataclass(slots=True)
class OpenPosition:
    exit_time: datetime
    symbol: str
    window: str
    net_r: float
    risk_per_trade_pct: float
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


def build_adaptive_sizing_report(config: AdaptiveSizingConfig) -> dict[str, object]:
    """Build an adaptive sizing stress report from replay accepted trades."""

    if config.initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if config.max_drawdown_gate_pct <= 0:
        raise ValueError("max_drawdown_gate_pct must be positive")
    if not config.scenarios:
        raise ValueError("scenarios must not be empty")
    trades = _load_trades(config.windows)
    scenarios = []
    for scenario in config.scenarios:
        aggregate = _simulate(config.initial_equity, scenario, trades)
        window_replays = [
            _simulate(
                config.initial_equity,
                scenario,
                [trade for trade in trades if trade.window == window.name],
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
                "passes_window_replay_stability": all(
                    bool(row["accepted_trade_count"] > 0)
                    and bool(row["total_return_pct"] > 0)
                    and bool(row["max_drawdown_pct"] <= config.max_drawdown_gate_pct)
                    for row in window_replays
                ),
                "passes_symbol_average_r_breadth": _passes_symbol_average_r_breadth(aggregate),
            }
        )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "initial_equity": config.initial_equity,
        "max_drawdown_gate_pct": config.max_drawdown_gate_pct,
        "windows": [
            {
                "name": window.name,
                "replay_report_path": str(window.replay_report_path),
            }
            for window in config.windows
        ],
        "trade_count": len(trades),
        "scenarios": scenarios,
        "decision": _decision(scenarios),
    }
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _load_trades(windows: tuple[ReplayWindowConfig, ...]) -> list[Trade]:
    trades: list[Trade] = []
    for window in windows:
        replay_report = _read_json(window.replay_report_path)
        for replay in replay_report["replays"]:
            replay_item = dict(replay)
            trades_path = window.replay_report_path.parent / str(
                replay_item["accepted_trades_path"]
            )
            trades.extend(
                Trade.from_row(dict(row), window.name)
                for row in pq.read_table(trades_path).to_pylist()
            )
    return sorted(trades, key=lambda trade: (trade.decision_time, trade.symbol))


def _simulate(
    initial_equity: float,
    scenario: AdaptiveSizingScenario,
    trades: list[Trade],
) -> dict[str, object]:
    _validate_scenario(scenario)
    state = SimulationState(equity=initial_equity, peak_equity=initial_equity)
    open_positions: list[OpenPosition] = []
    day_counts: dict[str, int] = defaultdict(int)
    monthly: dict[str, dict[str, object]] = {}
    symbols: dict[str, dict[str, object]] = {}
    windows: dict[str, dict[str, object]] = {}
    accepted_trade_count = 0
    skipped_trade_count = 0
    risk_sum = 0.0
    max_open_trades = 0

    for trade in trades:
        _settle_positions(state, open_positions, trade.decision_time, monthly, symbols, windows)
        risk_pct = _risk_for_trade(scenario, state, trade, day_counts)
        if risk_pct <= 0:
            skipped_trade_count += 1
            _increment_skip(windows, trade.window)
            continue
        day_counts[_day_key(trade.decision_time)] += 1
        pnl = state.equity * risk_pct * trade.net_r
        open_positions.append(
            OpenPosition(
                exit_time=trade.exit_time,
                symbol=trade.symbol,
                window=trade.window,
                net_r=trade.net_r,
                risk_per_trade_pct=risk_pct,
                pnl=pnl,
            )
        )
        accepted_trade_count += 1
        risk_sum += risk_pct
        max_open_trades = max(max_open_trades, len(open_positions))

    _settle_positions(
        state, open_positions, datetime.max.replace(tzinfo=UTC), monthly, symbols, windows
    )
    monthly_rows = [
        {"month": month, **_finalize_group(row)} for month, row in sorted(monthly.items())
    ]
    symbol_rows = [_finalize_named_group(symbol, row) for symbol, row in sorted(symbols.items())]
    window_rows = [_finalize_named_group(window, row) for window, row in sorted(windows.items())]
    return {
        "name": scenario.name,
        "description": scenario.description,
        "base_risk_per_trade_pct": scenario.base_risk_per_trade_pct,
        "drawdown_risk_steps": [
            {
                "at_drawdown_pct": step.at_drawdown_pct,
                "risk_per_trade_pct": step.risk_per_trade_pct,
            }
            for step in scenario.drawdown_risk_steps
        ],
        "max_trades_per_day": scenario.max_trades_per_day,
        "allowed_symbols": list(scenario.allowed_symbols),
        "initial_equity": initial_equity,
        "final_equity": state.equity,
        "total_pnl": state.equity - initial_equity,
        "total_return_pct": (state.equity / initial_equity) - 1,
        "max_drawdown_pct": state.max_drawdown_pct,
        "accepted_trade_count": accepted_trade_count,
        "skipped_trade_count": skipped_trade_count,
        "average_risk_per_trade_pct": risk_sum / accepted_trade_count
        if accepted_trade_count
        else 0.0,
        "max_open_trades": max_open_trades,
        "monthly": monthly_rows,
        "symbols": symbol_rows,
        "windows": window_rows,
        "worst_month": min(monthly_rows, key=lambda row: float(row["return_pct"]))
        if monthly_rows
        else None,
    }


def _settle_positions(
    state: SimulationState,
    open_positions: list[OpenPosition],
    until: datetime,
    monthly: dict[str, dict[str, object]],
    symbols: dict[str, dict[str, object]],
    windows: dict[str, dict[str, object]],
) -> None:
    still_open: list[OpenPosition] = []
    for position in open_positions:
        if position.exit_time > until:
            still_open.append(position)
            continue
        state.equity += position.pnl
        state.peak_equity = max(state.peak_equity, state.equity)
        state.max_drawdown_pct = max(state.max_drawdown_pct, state.current_drawdown_pct)
        _record_trade(
            monthly,
            _month_key(position.exit_time),
            state.equity - position.pnl,
            state.equity,
            position,
        )
        _record_trade(symbols, position.symbol, state.equity - position.pnl, state.equity, position)
        _record_trade(windows, position.window, state.equity - position.pnl, state.equity, position)
    open_positions[:] = still_open


def _risk_for_trade(
    scenario: AdaptiveSizingScenario,
    state: SimulationState,
    trade: Trade,
    day_counts: dict[str, int],
) -> float:
    symbol_blocked = bool(scenario.allowed_symbols) and trade.symbol not in scenario.allowed_symbols
    day_cap_reached = (
        scenario.max_trades_per_day is not None
        and day_counts[_day_key(trade.decision_time)] >= scenario.max_trades_per_day
    )
    if symbol_blocked or day_cap_reached:
        return 0.0
    risk = scenario.base_risk_per_trade_pct
    for step in sorted(
        scenario.drawdown_risk_steps,
        key=lambda item: item.at_drawdown_pct,
        reverse=True,
    ):
        if state.current_drawdown_pct >= step.at_drawdown_pct:
            risk = min(risk, step.risk_per_trade_pct)
            break
    return risk


def _passes_symbol_average_r_breadth(scenario: dict[str, object]) -> bool:
    symbols = [dict(row) for row in scenario["symbols"]]
    return bool(symbols) and all(float(row["average_r"]) > 0 for row in symbols)


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
            "skipped_trade_count": 0,
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


def _increment_skip(groups: dict[str, dict[str, object]], key: str) -> None:
    row = groups.setdefault(
        key,
        {
            "start_equity": 0.0,
            "end_equity": 0.0,
            "pnl": 0.0,
            "accepted_trade_count": 0,
            "skipped_trade_count": 0,
            "r_sum": 0.0,
            "wins": 0,
            "gross_win_r": 0.0,
            "gross_loss_r": 0.0,
        },
    )
    row["skipped_trade_count"] = int(row["skipped_trade_count"]) + 1


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
        "skipped_trade_count": int(row["skipped_trade_count"]),
        "average_r": float(row["r_sum"]) / accepted if accepted else 0.0,
        "win_rate": int(row["wins"]) / accepted if accepted else 0.0,
        "profit_factor": float(row["gross_win_r"]) / gross_loss_r if gross_loss_r else float("inf"),
    }


def _decision(scenarios: list[dict[str, object]]) -> dict[str, object]:
    passing = [
        scenario
        for scenario in scenarios
        if bool(scenario["passes_drawdown_gate"])
        and bool(scenario["passes_window_replay_stability"])
        and bool(scenario["passes_symbol_average_r_breadth"])
        and float(scenario["total_return_pct"]) > 0
    ]
    best = max(passing, key=lambda row: float(row["total_return_pct"])) if passing else None
    return {
        "research_only": True,
        "live_trading_approved": False,
        "working_model": False,
        "best_paper_candidate": best["name"] if best else None,
        "notes": (
            "Historical sizing evidence only; a passing scenario can justify a paper pack update, "
            "not live trading approval."
        ),
    }


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        "| scenario | final equity | return | max DD | accepted | skipped | "
        "avg risk | window reset | symbol avg R |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        lines.append(
            "| "
            f"`{item['name']}` | "
            f"${float(item['final_equity']):,.2f} | "
            f"{float(item['total_return_pct']):.2%} | "
            f"{float(item['max_drawdown_pct']):.2%} | "
            f"{int(item['accepted_trade_count'])} | "
            f"{int(item['skipped_trade_count'])} | "
            f"{float(item['average_risk_per_trade_pct']):.3%} | "
            f"{'pass' if item['passes_window_replay_stability'] else 'fail'} | "
            f"{'pass' if item['passes_symbol_average_r_breadth'] else 'fail'} |"
        )
    lines.extend(["", "## Window Reset Replays", ""])
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        lines.extend(
            [
                f"### {item['name']}",
                "",
                "| window | final equity | return | max DD | accepted | skipped | avg R |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for window in item["window_replays"]:
            window_item = dict(window)
            lines.append(
                "| "
                f"`{window_item['window']}` | "
                f"${float(window_item['final_equity']):,.2f} | "
                f"{float(window_item['total_return_pct']):.2%} | "
                f"{float(window_item['max_drawdown_pct']):.2%} | "
                f"{int(window_item['accepted_trade_count'])} | "
                f"{int(window_item['skipped_trade_count'])} | "
                f"{_average_r(window_item):.4f} |"
            )
        lines.append("")
    decision = dict(payload["decision"])
    lines.extend(
        [
            "## Decision",
            "",
            f"- Research only: `{decision['research_only']}`",
            f"- Live trading approved: `{decision['live_trading_approved']}`",
            f"- Best paper candidate: `{decision['best_paper_candidate']}`",
            "",
            "Backtest sizing evidence can support a paper-pack update, "
            "but does not approve live trading.",
            "",
        ]
    )
    return "\n".join(lines)


def _average_r(row: dict[str, object]) -> float:
    windows = row.get("windows", [])
    if isinstance(windows, list) and len(windows) == 1:
        return float(dict(windows[0]).get("average_r", 0.0))
    accepted = int(row.get("accepted_trade_count", 0))
    return (
        sum(
            float(dict(symbol).get("average_r", 0.0))
            * int(dict(symbol).get("accepted_trade_count", 0))
            for symbol in row.get("symbols", [])
        )
        / accepted
        if accepted
        else 0.0
    )


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(path)
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _validate_scenario(scenario: AdaptiveSizingScenario) -> None:
    if scenario.base_risk_per_trade_pct <= 0:
        raise ValueError("base_risk_per_trade_pct must be positive")
    if scenario.max_trades_per_day is not None and scenario.max_trades_per_day <= 0:
        raise ValueError("max_trades_per_day must be positive when set")
    for step in scenario.drawdown_risk_steps:
        if step.at_drawdown_pct < 0:
            raise ValueError("drawdown step threshold must be non-negative")
        if step.risk_per_trade_pct < 0:
            raise ValueError("drawdown step risk must be non-negative")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    payload = build_adaptive_sizing_report(AdaptiveSizingConfig.from_path(args.config))
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        print(
            f"name={item['name']} "
            f"final=${float(item['final_equity']):.2f} "
            f"return={float(item['total_return_pct']):.2%} "
            f"max_dd={float(item['max_drawdown_pct']):.2%} "
            f"accepted={int(item['accepted_trade_count'])} "
            f"skipped={int(item['skipped_trade_count'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
