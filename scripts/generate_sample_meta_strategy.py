#!/usr/bin/env python
"""Generate a deterministic sample meta-strategy report."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from crypto_trade_research.meta_strategy import (
    MetaStrategyConfig,
    ModelEstimate,
    candidate_key,
    evaluate_meta_strategy,
    generate_trend_pullback_candidates,
    select_threshold_on_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    validation_features = [
        _feature_row(1, 101, 100, -0.01, 0.45),
        _feature_row(2, 102, 100, -0.01, 0.55),
        _feature_row(3, 103, 100, -0.01, 0.35),
    ]
    validation_candidates = generate_trend_pullback_candidates(
        validation_features,
        pullback_return_threshold=-0.005,
        max_range_position=0.6,
    )
    validation_estimates = {
        candidate_key(validation_candidates[0]): ModelEstimate(0.55, 0.5, 0.2),
        candidate_key(validation_candidates[1]): ModelEstimate(0.65, 0.5, 0.2),
        candidate_key(validation_candidates[2]): ModelEstimate(0.75, 0.5, 0.2),
    }
    selected_config = select_threshold_on_validation(
        validation_candidates,
        validation_estimates,
        candidate_thresholds=(0.5, 0.6, 0.7),
        base_config=MetaStrategyConfig(
            probability_threshold=0.5,
            expected_r_threshold=0.1,
            max_stopout_risk=0.5,
            max_symbol_exposure=0.02,
            risk_per_trade_pct=0.01,
        ),
    )

    test_candidates = generate_trend_pullback_candidates(
        [
            _feature_row(4, 104, 101, -0.01, 0.40),
            _feature_row(5, 105, 101, -0.01, 0.50),
        ],
        pullback_return_threshold=-0.005,
        max_range_position=0.6,
    )
    test_candidates = [
        test_candidates[0],
        replace(test_candidates[1], rule_only_gross_r=-1.0),
    ]
    test_estimates = {
        candidate_key(test_candidates[0]): ModelEstimate(0.72, 0.4, 0.2),
        candidate_key(test_candidates[1]): ModelEstimate(0.62, 0.4, 0.2),
    }
    report = evaluate_meta_strategy(test_candidates, test_estimates, selected_config)
    payload = report.to_report_dict()
    (args.output_dir / "meta_strategy_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "meta_strategy_report.md").write_text(
        _markdown_report(payload),
        encoding="utf-8",
    )
    print(args.output_dir / "meta_strategy_report.json")


def _feature_row(
    day: int,
    close: float,
    ma: float,
    return_1: float,
    range_position: float,
) -> dict[str, object]:
    from datetime import UTC, datetime

    return {
        "decision_time": datetime(2026, 1, day, tzinfo=UTC),
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "close": close,
        "ma_3": ma,
        "ma_slope_3": 0.01,
        "return_1": return_1,
        "range_position_3": range_position,
        "volatility_expansion_3": 1.0,
    }


def _markdown_report(payload: dict[str, object]) -> str:
    rule = payload["rule_only"]["metrics"]
    filtered = payload["ml_filtered"]["metrics"]
    return "\n".join(
        [
            "# Meta-Strategy Report",
            "",
            "ML filters candidate trades; deterministic risk gates still decide eligibility.",
            "",
            "| Strategy | Trades | Average R | Max drawdown |",
            "| --- | ---: | ---: | ---: |",
            (
                f"| Rule-only | {rule['trade_count']} | {rule['average_r']:.4f} | "
                f"{rule['max_drawdown_pct']:.4%} |"
            ),
            (
                f"| ML-filtered | {filtered['trade_count']} | {filtered['average_r']:.4f} | "
                f"{filtered['max_drawdown_pct']:.4%} |"
            ),
            "",
            f"Rejected trades: {payload['rejected_trade_count']}",
            "",
        ]
    )


if __name__ == "__main__":
    main()
