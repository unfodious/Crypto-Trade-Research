#!/usr/bin/env python
"""Generate deterministic sample experiment registry records."""

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from crypto_trade_research.tracking import (
    CostAssumptions,
    ExperimentRecord,
    ModelVersion,
    PromotionGateInputs,
    TimeWindow,
    evaluate_promotion_gates,
    format_experiment_list,
    list_experiments,
    write_experiment_record,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    commit = _git_commit()
    promoted = _record(
        version="2026-01-07T000000Z",
        created_at=datetime(2026, 1, 7, tzinfo=UTC),
        commit=commit,
        gate_inputs=PromotionGateInputs(
            model_average_r=0.42,
            rule_only_average_r=0.18,
            naive_average_r=0.0,
            walk_forward_average_r=0.31,
            max_drawdown_pct=0.04,
            max_drawdown_duration_bars=3,
            max_allowed_drawdown_pct=0.08,
            max_allowed_drawdown_duration_bars=10,
            leakage_checks_passed=True,
            stability_checks_passed=True,
            paper_trading_plan_path="docs/paper-trading-plan.md",
        ),
    )
    rejected = _record(
        version="2026-01-08T000000Z",
        created_at=datetime(2026, 1, 8, tzinfo=UTC),
        commit=commit,
        gate_inputs=PromotionGateInputs(
            model_average_r=0.05,
            rule_only_average_r=0.18,
            naive_average_r=0.0,
            walk_forward_average_r=0.01,
            max_drawdown_pct=0.12,
            max_drawdown_duration_bars=15,
            max_allowed_drawdown_pct=0.08,
            max_allowed_drawdown_duration_bars=10,
            leakage_checks_passed=True,
            stability_checks_passed=False,
            paper_trading_plan_path="",
        ),
    )

    promoted_path = write_experiment_record(args.registry_dir, promoted)
    rejected_path = write_experiment_record(args.registry_dir, rejected)
    print(promoted_path)
    print(rejected_path)
    print(format_experiment_list(list_experiments(args.registry_dir)))


def _record(
    version: str,
    created_at: datetime,
    commit: str,
    gate_inputs: PromotionGateInputs,
) -> ExperimentRecord:
    decision = evaluate_promotion_gates(gate_inputs)
    return ExperimentRecord(
        model=ModelVersion(
            model_id="linear_probability_threshold",
            version=version,
            model_type="linear_probability_threshold",
        ),
        research_git_commit=commit,
        dataset_manifest_path="data/generated/sample_market_dataset/manifest.json",
        dataset_manifest_version="sample_market_dataset@2026-01-01",
        feature_names=("setup_score", "noise"),
        feature_code_version="features.core.v1",
        label_config={
            "kind": "target_before_stop",
            "target_r": 1.5,
            "stop_r": 1.0,
            "horizon_bars": 12,
        },
        train_window=TimeWindow("2026-01-01T00:00:00Z", "2026-01-04T00:00:00Z"),
        validation_window=TimeWindow("2026-01-05T00:00:00Z", "2026-01-05T00:00:00Z"),
        test_window=TimeWindow("2026-01-06T00:00:00Z", "2026-01-06T00:00:00Z"),
        cost_assumptions=CostAssumptions(
            fee_bps=4.0,
            slippage_bps=3.0,
            funding_bps=0.0,
            notes="fake sample assumptions only",
        ),
        metrics={
            "average_r": gate_inputs.model_average_r,
            "rule_only_average_r": gate_inputs.rule_only_average_r,
            "naive_average_r": gate_inputs.naive_average_r,
            "walk_forward_average_r": gate_inputs.walk_forward_average_r,
            "max_drawdown_pct": gate_inputs.max_drawdown_pct,
            "max_drawdown_duration_bars": gate_inputs.max_drawdown_duration_bars,
        },
        walk_forward_report_path="data/generated/sample_backtest/report.json",
        decision=decision,
        created_at=created_at,
    )


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "unknown"
    return result.stdout.strip() or "unknown"


if __name__ == "__main__":
    main()
