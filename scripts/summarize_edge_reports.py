"""Print the report tables for the alt-data / cross-section study.

Reads the JSON that `crypto-trade-run-edge-study` and
`crypto-trade-run-cross-section` write and emits the Markdown rows used in
`docs/research/`, so the document and the run cannot drift apart by hand.

    uv run python scripts/summarize_edge_reports.py reports/edge-study/*.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _row(label: str, after: dict, before: dict) -> str:
    return (
        f"| {label} | {after['trades']:.0f} | {after['win_rate'] * 100:.1f} | "
        f"{after['profit_factor']:.2f} | {after['expectancy_r']:+.4f} | "
        f"{before['expectancy_r']:+.4f} | {after['total_return'] * 100:+.1f}% | "
        f"{before['total_return'] * 100:+.1f}% | {after['max_drawdown'] * 100:.1f}% | "
        f"{after['sharpe']:+.2f} |"
    )


def summarize(path: Path) -> None:
    report = json.loads(path.read_text())
    print(f"\n### {path.name}")
    print(f"feature_set={report.get('feature_set')} alt_data={report.get('alt_data')} "
          f"features={len(report.get('feature_columns', []))}")
    print(json.dumps(report.get("sample_sizes", {}), indent=1, default=str))
    print("\n| strategy | trades | win% | PF | E[R] after | E[R] before | ret after "
          "| ret before | maxDD | Sharpe |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for evaluation in report.get("evaluations", []):
        print(_row(evaluation["label"], evaluation["after_costs"], evaluation["before_costs"]))

    folds = report.get("folds", [])
    if folds:
        print("\n| fold | test window | train n | test n | train AUC | test AUC | trades | E[R] |")
        print("|---|---|---|---|---|---|---|---|")
        for fold in folds:
            if fold.get("selectivity") not in (None, 0.5):
                continue
            metrics = fold["metrics_after_costs"]
            print(
                f"| {fold['fold']} | {fold['test_start'][:10]} .. {fold['test_end'][:10]} | "
                f"{fold['train_size']} | {fold['test_size']} | {fold['train_auc']:.3f} | "
                f"**{fold['auc']:.3f}** | {metrics['trades']:.0f} | "
                f"{metrics['expectancy_r']:+.4f} |"
            )

    significance = report.get("significance", {})
    if significance:
        print("\nsignificance:")
        print(json.dumps(significance, indent=1, default=str))

    for name, rows in report.get("breakdowns", {}).items():
        print(f"\n{name}:")
        for row in rows:
            key = next(iter(row))
            print(
                f"  {row[key]:<10} n={row['trades']:<5} "
                f"E[R]after={row['expectancy_r_after_costs']:+.4f} "
                f"E[R]before={row['expectancy_r_before_costs']:+.4f}"
            )


def main(argv: list[str]) -> int:
    for argument in argv[1:]:
        summarize(Path(argument))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
