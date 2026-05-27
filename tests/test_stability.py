import json
from pathlib import Path

from crypto_trade_research.evaluation.stability import (
    StabilityThresholds,
    evaluate_candidate_stability,
    evaluate_candidate_stability_from_files,
    segment_breakdown_from_strategy_report,
)


def test_stability_report_rejects_lucky_slice_and_drawdown_concentration() -> None:
    report = evaluate_candidate_stability(
        candidate_row={
            "experiment_name": "candidate",
            "oos_model_average_r": 0.12,
            "oos_rule_only_average_r": 0.02,
            "trade_count": 200,
            "max_drawdown_pct": 0.30,
        },
        leaderboard_rows=[
            {
                "experiment_name": "candidate_low",
                "oos_model_average_r": -0.05,
                "trade_count": 180,
            },
            {
                "experiment_name": "candidate_high",
                "oos_model_average_r": -0.08,
                "trade_count": 220,
            },
        ],
        segment_breakdown={
            "model_by_symbol": {
                "BTCUSDT": {"average_r": 0.5, "trade_count": 160},
                "ETHUSDT": {"average_r": -0.4, "trade_count": 160},
                "SOLUSDT": {"average_r": -0.2, "trade_count": 160},
            },
            "model_by_session": {
                "asia": {"average_r": 0.2, "trade_count": 120},
                "europe": {"average_r": -0.1, "trade_count": 120},
                "us": {"average_r": -0.2, "trade_count": 120},
            },
            "model_by_day": {
                "2026-05-01": {"average_r": 1.0, "trade_count": 50},
                "2026-05-02": {"average_r": -0.2, "trade_count": 50},
            },
        },
        thresholds=StabilityThresholds(
            max_drawdown_pct=0.08,
            min_trade_count=100,
            min_positive_symbol_fraction=0.50,
            min_positive_session_fraction=0.50,
            max_top_day_profit_share=0.75,
            min_positive_nearby_fraction=0.50,
        ),
    )

    assert report.status == "reject"
    failed = {gate.name for gate in report.gates if not gate.passed}
    assert "drawdown_within_limit" in failed
    assert "symbol_breadth" in failed
    assert "session_breadth" in failed
    assert "nearby_sensitivity" in failed


def test_stability_report_passes_broad_positive_candidate() -> None:
    report = evaluate_candidate_stability(
        candidate_row={
            "experiment_name": "candidate",
            "oos_model_average_r": 0.18,
            "oos_rule_only_average_r": 0.04,
            "trade_count": 600,
            "max_drawdown_pct": 0.04,
        },
        leaderboard_rows=[
            {
                "experiment_name": "candidate_low",
                "oos_model_average_r": 0.08,
                "trade_count": 520,
            },
            {
                "experiment_name": "candidate_high",
                "oos_model_average_r": 0.06,
                "trade_count": 480,
            },
        ],
        segment_breakdown={
            "model_by_symbol": {
                "BTCUSDT": {"average_r": 0.12, "trade_count": 200},
                "ETHUSDT": {"average_r": 0.07, "trade_count": 200},
                "SOLUSDT": {"average_r": -0.01, "trade_count": 200},
            },
            "model_by_session": {
                "asia": {"average_r": 0.05, "trade_count": 200},
                "europe": {"average_r": 0.08, "trade_count": 200},
                "us": {"average_r": 0.03, "trade_count": 200},
            },
            "model_by_day": {
                "2026-05-01": {"average_r": 0.2, "trade_count": 100},
                "2026-05-02": {"average_r": 0.1, "trade_count": 100},
                "2026-05-03": {"average_r": 0.05, "trade_count": 100},
            },
        },
        thresholds=StabilityThresholds(
            max_drawdown_pct=0.08,
            min_trade_count=100,
            min_positive_symbol_fraction=0.50,
            min_positive_session_fraction=0.50,
            max_top_day_profit_share=0.75,
            min_positive_nearby_fraction=0.50,
        ),
    )

    assert report.status == "pass"
    assert all(gate.passed for gate in report.gates)


def test_segment_breakdown_from_strategy_report_groups_symbol_session_and_day() -> None:
    breakdown = segment_breakdown_from_strategy_report(
        {
            "trades": [
                {
                    "decision_time": "2026-05-01T01:00:00Z",
                    "symbol": "BTCUSDT",
                    "net_r": 1.0,
                },
                {
                    "decision_time": "2026-05-01T09:00:00Z",
                    "symbol": "ETHUSDT",
                    "net_r": -1.0,
                },
                {
                    "decision_time": "2026-05-02T17:00:00Z",
                    "symbol": "BTCUSDT",
                    "net_r": 2.0,
                },
            ]
        }
    )

    assert breakdown["model_by_symbol"]["BTCUSDT"]["trade_count"] == 2
    assert breakdown["model_by_symbol"]["BTCUSDT"]["average_r"] == 1.5
    assert breakdown["model_by_session"]["asia"]["trade_count"] == 1
    assert breakdown["model_by_session"]["europe"]["average_r"] == -1.0
    assert breakdown["model_by_session"]["us"]["win_rate"] == 1.0
    assert breakdown["model_by_day"]["2026-05-01"]["trade_count"] == 2


def test_evaluate_candidate_stability_from_files_writes_artifact(tmp_path: Path) -> None:
    leaderboard_path = tmp_path / "leaderboard.json"
    baseline_report_path = tmp_path / "baseline_report.json"
    output_path = tmp_path / "stability.json"
    leaderboard_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "experiment_name": "candidate",
                        "oos_model_average_r": 0.18,
                        "oos_rule_only_average_r": 0.04,
                        "trade_count": 6,
                        "max_drawdown_pct": 0.02,
                    },
                    {
                        "experiment_name": "nearby",
                        "oos_model_average_r": 0.05,
                        "trade_count": 5,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    baseline_report_path.write_text(
        json.dumps(
            {
                "strategies": {
                    "expected_r_ridge_top3_oos": {
                        "trades": [
                            {
                                "decision_time": "2026-05-01T01:00:00Z",
                                "symbol": "BTCUSDT",
                                "net_r": 1.0,
                            },
                            {
                                "decision_time": "2026-05-01T09:00:00Z",
                                "symbol": "ETHUSDT",
                                "net_r": 1.0,
                            },
                            {
                                "decision_time": "2026-05-01T17:00:00Z",
                                "symbol": "SOLUSDT",
                                "net_r": 1.0,
                            },
                            {
                                "decision_time": "2026-05-02T01:00:00Z",
                                "symbol": "BTCUSDT",
                                "net_r": 1.0,
                            },
                            {
                                "decision_time": "2026-05-02T09:00:00Z",
                                "symbol": "ETHUSDT",
                                "net_r": 1.0,
                            },
                            {
                                "decision_time": "2026-05-02T17:00:00Z",
                                "symbol": "SOLUSDT",
                                "net_r": -1.0,
                            },
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    payload = evaluate_candidate_stability_from_files(
        leaderboard_path=leaderboard_path,
        baseline_report_path=baseline_report_path,
        candidate_name="candidate",
        strategy_name="expected_r_ridge_top3_oos",
        output_path=output_path,
        thresholds=StabilityThresholds(min_trade_count=5),
    )

    assert output_path.exists()
    assert payload["stability_report"]["status"] == "pass"
    assert payload["segment_breakdown"]["model_by_session"]["us"]["trade_count"] == 2
