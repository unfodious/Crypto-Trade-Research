from datetime import UTC, datetime

from scripts.generate_sample_baselines import _markdown_report

from crypto_trade_research.models.baselines import (
    BaselineConfig,
    ModelSample,
    train_and_evaluate_baselines,
)


def _ts(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def _sample(day: int, score: float, outcome_r: float) -> ModelSample:
    return ModelSample(
        decision_time=_ts(day),
        symbol="BTCUSDT",
        timeframe="1d",
        side="long",
        features={"setup_score": score, "noise": 1.0 - score},
        target_before_stop=outcome_r > 0,
        realized_r_after_costs=outcome_r,
    )


def _multi_sample(
    day: int,
    setup_score: float,
    context_score: float,
    outcome_r: float,
) -> ModelSample:
    return ModelSample(
        decision_time=_ts(day),
        symbol="BTCUSDT",
        timeframe="1d",
        side="long",
        features={"setup_score": setup_score, "context_score": context_score},
        target_before_stop=outcome_r > 0,
        realized_r_after_costs=outcome_r,
    )


def test_baseline_report_compares_no_trade_rule_only_and_linear_model() -> None:
    samples = [
        _sample(1, 0.9, 1.0),
        _sample(2, 0.8, 1.0),
        _sample(3, 0.2, -1.0),
        _sample(4, 0.1, -1.0),
        _sample(5, 0.85, 1.0),
        _sample(6, 0.15, -1.0),
    ]

    report = train_and_evaluate_baselines(
        samples,
        BaselineConfig(
            feature_names=("setup_score", "noise"),
            decision_feature="setup_score",
            train_end=_ts(4),
            validation_end=_ts(5),
            test_end=_ts(6),
            probability_threshold=0.5,
        ),
    )

    assert [split.name for split in report.splits] == ["train", "validation", "test"]
    assert report.model_metadata["feature_names"] == ["setup_score", "noise"]
    assert report.model_metadata["train_window"] == ["2026-01-01T00:00:00Z", "2026-01-04T00:00:00Z"]
    assert report.strategy_reports["no_trade"].metrics.trade_count == 0
    assert report.strategy_reports["rule_only"].metrics.trade_count == 6
    assert report.strategy_reports["linear_probability"].metrics.trade_count == 3
    assert report.strategy_reports["linear_probability"].metrics.average_r > 0
    assert report.strategy_reports["rule_only_oos"].metrics.trade_count == 2
    assert report.strategy_reports["linear_probability_oos"].metrics.trade_count == 1
    assert "multifeature_ridge_oos" in report.strategy_reports
    assert report.model_metadata["multifeature_model_type"] == "ridge_probability"
    assert report.strategy_reports["linear_probability_oos"].metrics.average_r == 1.0
    assert report.feature_importance[0]["feature"] == "setup_score"
    linear_report = report.to_report_dict()["strategies"]["linear_probability"]
    assert linear_report["metrics"]["trade_count"] == 3
    oos_report = report.to_report_dict()["strategies"]["linear_probability_oos"]
    assert oos_report["sample_scope"] == "validation_test"
    assert oos_report["metrics"]["trade_count"] == 1


def test_multifeature_ridge_uses_context_feature_and_validation_threshold() -> None:
    samples = [
        _multi_sample(1, setup_score=0.1, context_score=1.0, outcome_r=1.0),
        _multi_sample(2, setup_score=0.9, context_score=0.0, outcome_r=-1.0),
        _multi_sample(3, setup_score=0.2, context_score=1.0, outcome_r=1.0),
        _multi_sample(4, setup_score=0.8, context_score=0.0, outcome_r=-1.0),
        _multi_sample(5, setup_score=0.7, context_score=1.0, outcome_r=1.0),
        _multi_sample(6, setup_score=0.6, context_score=0.0, outcome_r=-1.0),
    ]

    report = train_and_evaluate_baselines(
        samples,
        BaselineConfig(
            feature_names=("setup_score", "context_score"),
            decision_feature="setup_score",
            train_end=_ts(4),
            validation_end=_ts(5),
            test_end=_ts(6),
            probability_threshold=0.5,
        ),
    )

    assert report.strategy_reports["multifeature_ridge_oos"].metrics.trade_count == 1
    assert report.strategy_reports["multifeature_ridge_oos"].metrics.average_r == 1.0
    assert report.model_metadata["multifeature_probability_threshold"] >= 0.4
    assert any(
        item["feature"] == "context_score" and item["model"] == "multifeature_ridge"
        for item in report.feature_importance
    )


def test_baseline_report_rejects_in_sample_only_performance() -> None:
    samples = [
        _sample(1, 0.9, 1.0),
        _sample(2, 0.8, 1.0),
        _sample(3, 0.2, -1.0),
        _sample(4, 0.1, -1.0),
        _sample(5, 0.85, -1.0),
        _sample(6, 0.95, -1.0),
    ]

    report = train_and_evaluate_baselines(
        samples,
        BaselineConfig(
            feature_names=("setup_score",),
            decision_feature="setup_score",
            train_end=_ts(4),
            validation_end=_ts(5),
            test_end=_ts(6),
            probability_threshold=0.5,
        ),
    )

    assert report.model_metadata["oos_average_r"] < 0
    assert report.decision == "reject"
    assert report.rejection_reason == "model edge failed outside the training window"


def test_baseline_markdown_leads_with_out_of_sample_metrics() -> None:
    samples = [
        _sample(1, 0.9, 1.0),
        _sample(2, 0.8, 1.0),
        _sample(3, 0.2, -1.0),
        _sample(4, 0.1, -1.0),
        _sample(5, 0.85, 1.0),
        _sample(6, 0.15, -1.0),
    ]
    payload = train_and_evaluate_baselines(
        samples,
        BaselineConfig(
            feature_names=("setup_score",),
            decision_feature="setup_score",
            train_end=_ts(4),
            validation_end=_ts(5),
            test_end=_ts(6),
            probability_threshold=0.5,
        ),
    ).to_report_dict()

    markdown = _markdown_report(payload)

    assert markdown.index("## Out-of-Sample") < markdown.index("## Combined")
    assert "linear_probability_oos" in markdown


def test_baseline_training_requires_time_ordered_splits() -> None:
    samples = [_sample(1, 0.9, 1.0), _sample(2, 0.2, -1.0)]

    report = train_and_evaluate_baselines(
        samples,
        BaselineConfig(
            feature_names=("setup_score",),
            decision_feature="setup_score",
            train_end=_ts(1),
            validation_end=_ts(1),
            test_end=_ts(2),
            probability_threshold=0.5,
        ),
    )

    assert report.splits[0].end <= report.splits[1].end <= report.splits[2].end
