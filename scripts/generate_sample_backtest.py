#!/usr/bin/env python
"""Generate a deterministic sample walk-forward research backtest report."""

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.backtest import BacktestConfig, SignalRow, evaluate_signal_strategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    signals = [
        SignalRow.from_iso("2026-01-01T00:00:00Z", "BTCUSDT", "1d", "long", 2.0),
        SignalRow.from_iso("2026-01-02T00:00:00Z", "BTCUSDT", "1d", "short", -1.0),
        SignalRow.from_iso("2026-01-03T00:00:00Z", "BTCUSDT", "1d", "flat", 0.0),
        SignalRow.from_iso("2026-01-04T00:00:00Z", "BTCUSDT", "1d", "long", 0.5),
    ]
    report = evaluate_signal_strategy(
        "sample_signal_strategy",
        signals,
        BacktestConfig(
            initial_equity=10_000,
            risk_per_trade_pct=0.01,
            fee_r=0.05,
            spread_r=0.02,
            slippage_r=0.03,
        ),
    )

    payload = report.to_report_dict()
    (args.output_dir / "report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pq.write_table(pa.Table.from_pylist(payload["trades"]), args.output_dir / "trades.parquet")
    pq.write_table(
        pa.Table.from_pylist(payload["equity_curve"]),
        args.output_dir / "equity_curve.parquet",
    )
    (args.output_dir / "report.md").write_text(_markdown_report(payload), encoding="utf-8")
    print(args.output_dir / "report.json")


def _markdown_report(payload: dict[str, object]) -> str:
    metrics = payload["metrics"]
    return "\n".join(
        [
            f"# Backtest Report: {payload['strategy_name']}",
            "",
            "Backtests are rejection evidence, not proof of live profitability.",
            "",
            "## Metrics",
            "",
            f"- Trade count: {metrics['trade_count']}",
            f"- Total return: {metrics['total_return_pct']:.4%}",
            f"- Average R: {metrics['average_r']:.4f}",
            f"- Win rate: {metrics['win_rate']:.4%}",
            f"- Profit factor: {metrics['profit_factor']:.4f}",
            f"- Max drawdown: {metrics['max_drawdown_pct']:.4%}",
            f"- Max concurrent positions: {metrics['max_concurrent_positions']}",
            f"- Max concurrent risk: {metrics['max_concurrent_risk_pct']:.4%}",
            "",
        ]
    )


if __name__ == "__main__":
    main()
