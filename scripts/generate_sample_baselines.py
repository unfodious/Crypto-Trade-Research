#!/usr/bin/env python
"""Generate a deterministic baseline model comparison report."""

import argparse
import json
from pathlib import Path

from crypto_trade_research.models import (
    BaselineConfig,
    ModelSample,
    train_and_evaluate_baselines,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    samples = [
        ModelSample.from_iso("2026-01-01T00:00:00Z", 0.9, 1.0),
        ModelSample.from_iso("2026-01-02T00:00:00Z", 0.8, 1.0),
        ModelSample.from_iso("2026-01-03T00:00:00Z", 0.2, -1.0),
        ModelSample.from_iso("2026-01-04T00:00:00Z", 0.1, -1.0),
        ModelSample.from_iso("2026-01-05T00:00:00Z", 0.85, 1.0),
        ModelSample.from_iso("2026-01-06T00:00:00Z", 0.15, -1.0),
    ]
    report = train_and_evaluate_baselines(
        samples,
        BaselineConfig(
            feature_names=("setup_score", "noise"),
            decision_feature="setup_score",
            train_end=samples[3].decision_time,
            validation_end=samples[4].decision_time,
            test_end=samples[5].decision_time,
            probability_threshold=0.5,
        ),
    )
    payload = report.to_report_dict()
    (args.output_dir / "baseline_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "baseline_report.md").write_text(_markdown_report(payload), encoding="utf-8")
    print(args.output_dir / "baseline_report.json")


def _markdown_report(payload: dict[str, object]) -> str:
    strategies = payload["strategies"]
    lines = [
        "# Baseline Model Report",
        "",
        f"Decision: {payload['decision']}",
        "",
        "| Strategy | Trades | Average R | Total Return |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, report in strategies.items():
        metrics = report["metrics"]
        lines.append(
            f"| {name} | {metrics['trade_count']} | "
            f"{metrics['average_r']:.4f} | {metrics['total_return_pct']:.4%} |"
        )
    lines.extend(
        [
            "",
            "Simple baselines must survive out-of-sample checks before deep models are justified.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
