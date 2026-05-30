"""Stress-test historical accepted trades under fixed-risk sizing scenarios."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

SCHEMA_VERSION = "research.sizing-stress.v1"


@dataclass(frozen=True, slots=True)
class SizingStressWindowConfig:
    name: str
    replay_report_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SizingStressWindowConfig:
        return cls(
            name=str(payload["name"]),
            replay_report_path=Path(str(payload["replay_report_path"])),
        )


@dataclass(frozen=True, slots=True)
class SizingStressConfig:
    report_name: str
    issue_id: str
    epic_id: str
    initial_equity: float
    fixed_risk_per_trade_pcts: tuple[float, ...]
    output_json_path: Path
    output_markdown_path: Path
    windows: tuple[SizingStressWindowConfig, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SizingStressConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            initial_equity=float(payload.get("initial_equity", 1000.0)),
            fixed_risk_per_trade_pcts=tuple(
                float(item) for item in payload["fixed_risk_per_trade_pcts"]
            ),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            windows=tuple(
                SizingStressWindowConfig.from_dict(dict(item)) for item in payload["windows"]
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> SizingStressConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_sizing_stress_report(config: SizingStressConfig) -> dict[str, object]:
    """Build a fixed-risk sizing stress report from historical accepted trades."""

    if config.initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if not config.fixed_risk_per_trade_pcts:
        raise ValueError("fixed_risk_per_trade_pcts must not be empty")
    trades = _load_window_trades(config.windows)
    scenarios = [
        _scenario_report(config.initial_equity, risk_pct, trades)
        for risk_pct in config.fixed_risk_per_trade_pcts
    ]
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "initial_equity": config.initial_equity,
        "windows": [
            {
                "name": window.name,
                "replay_report_path": str(window.replay_report_path),
            }
            for window in config.windows
        ],
        "trade_count": len(trades),
        "scenarios": scenarios,
        "decision": {
            "research_only": True,
            "live_trading_approved": False,
            "working_model": False,
            "notes": "Counterfactual fixed-risk sizing stress test only.",
        },
    }
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _load_window_trades(
    windows: tuple[SizingStressWindowConfig, ...],
) -> list[dict[str, object]]:
    trades: list[dict[str, object]] = []
    for window in windows:
        replay_report = _read_json(window.replay_report_path)
        for replay in replay_report["replays"]:
            replay_item = dict(replay)
            trades_path = window.replay_report_path.parent / str(
                replay_item["accepted_trades_path"]
            )
            for row in pq.read_table(trades_path).to_pylist():
                trades.append({**dict(row), "window": window.name})
    return sorted(trades, key=lambda row: (_as_datetime(row["decision_time"]), str(row["symbol"])))


def _scenario_report(
    initial_equity: float,
    fixed_risk_per_trade_pct: float,
    trades: list[dict[str, object]],
) -> dict[str, object]:
    if fixed_risk_per_trade_pct <= 0:
        raise ValueError("fixed risk percentages must be positive")
    equity = initial_equity
    peak = equity
    max_drawdown_pct = 0.0
    monthly: dict[str, dict[str, object]] = {}
    window_values: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        month = _month_key(trade["decision_time"])
        month_row = monthly.setdefault(
            month,
            {
                "month": month,
                "start_equity": equity,
                "trade_count": 0,
                "pnl": 0.0,
                "r_sum": 0.0,
                "wins": 0,
                "gross_win_r": 0.0,
                "gross_loss_r": 0.0,
            },
        )
        net_r = float(trade["net_r"])
        pnl = equity * fixed_risk_per_trade_pct * net_r
        equity += pnl
        peak = max(peak, equity)
        max_drawdown_pct = max(max_drawdown_pct, (peak - equity) / peak if peak else 0.0)
        month_row["trade_count"] = int(month_row["trade_count"]) + 1
        month_row["pnl"] = float(month_row["pnl"]) + pnl
        month_row["r_sum"] = float(month_row["r_sum"]) + net_r
        if net_r > 0:
            month_row["wins"] = int(month_row["wins"]) + 1
            month_row["gross_win_r"] = float(month_row["gross_win_r"]) + net_r
        elif net_r < 0:
            month_row["gross_loss_r"] = float(month_row["gross_loss_r"]) + abs(net_r)
        month_row["end_equity"] = equity
        window_values[str(trade["window"])].append(net_r)

    monthly_rows = [_finalize_month(row) for _, row in sorted(monthly.items())]
    return {
        "fixed_risk_per_trade_pct": fixed_risk_per_trade_pct,
        "initial_equity": initial_equity,
        "final_equity": equity,
        "total_pnl": equity - initial_equity,
        "total_return_pct": (equity / initial_equity) - 1,
        "max_drawdown_pct": max_drawdown_pct,
        "trade_count": len(trades),
        "worst_month": min(monthly_rows, key=lambda row: float(row["return_pct"]))
        if monthly_rows
        else None,
        "best_month": max(monthly_rows, key=lambda row: float(row["return_pct"]))
        if monthly_rows
        else None,
        "monthly": monthly_rows,
        "window_average_r": {
            window: sum(values) / len(values) for window, values in sorted(window_values.items())
        },
    }


def _finalize_month(row: dict[str, object]) -> dict[str, object]:
    trade_count = int(row["trade_count"])
    start_equity = float(row["start_equity"])
    end_equity = float(row.get("end_equity", start_equity))
    gross_loss_r = float(row["gross_loss_r"])
    return {
        "month": str(row["month"]),
        "start_equity": start_equity,
        "end_equity": end_equity,
        "pnl": float(row["pnl"]),
        "return_pct": (end_equity / start_equity) - 1 if start_equity else 0.0,
        "trade_count": trade_count,
        "average_r": float(row["r_sum"]) / trade_count if trade_count else 0.0,
        "win_rate": int(row["wins"]) / trade_count if trade_count else 0.0,
        "profit_factor": float(row["gross_win_r"]) / gross_loss_r if gross_loss_r else float("inf"),
    }


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        "| fixed risk | final equity | total PnL | return | max DD | worst month |",
        "| ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        worst = dict(item["worst_month"]) if item.get("worst_month") else {}
        lines.append(
            "| "
            f"{float(item['fixed_risk_per_trade_pct']):.2%} | "
            f"${float(item['final_equity']):,.2f} | "
            f"${float(item['total_pnl']):,.2f} | "
            f"{float(item['total_return_pct']):.2%} | "
            f"{float(item['max_drawdown_pct']):.2%} | "
            f"{worst.get('month', '')} ({float(worst.get('return_pct', 0.0)):.2%}) |"
        )
    lines.extend(["", "## Monthly", ""])
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        lines.extend(
            [
                f"### Fixed Risk {float(item['fixed_risk_per_trade_pct']):.2%}",
                "",
                "| month | trades | PnL | return | end equity | avg R |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for month in item["monthly"]:
            month_item = dict(month)
            lines.append(
                "| "
                f"{month_item['month']} | "
                f"{int(month_item['trade_count'])} | "
                f"${float(month_item['pnl']):,.2f} | "
                f"{float(month_item['return_pct']):.2%} | "
                f"${float(month_item['end_equity']):,.2f} | "
                f"{float(month_item['average_r']):.4f} |"
            )
        lines.append("")
    lines.append("Research-only counterfactual sizing stress. No live trading approval.")
    lines.append("")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(path)
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _month_key(value: object) -> str:
    return _as_datetime(value).strftime("%Y-%m")


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
    payload = build_sizing_stress_report(SizingStressConfig.from_path(args.config))
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        print(
            f"risk={float(item['fixed_risk_per_trade_pct']):.2%} "
            f"final=${float(item['final_equity']):.2f} "
            f"return={float(item['total_return_pct']):.2%} "
            f"max_dd={float(item['max_drawdown_pct']):.2%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
