from datetime import UTC, datetime

from scripts.generate_sample_baselines import _markdown_report

from crypto_trade_research.backtest import BacktestConfig
from crypto_trade_research.models.baselines import (
    BaselineConfig,
    ModelSample,
    _calibrate_probability_threshold,
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
    symbol: str = "BTCUSDT",
) -> ModelSample:
    return ModelSample(
        decision_time=_ts(day),
        symbol=symbol,
        timeframe="1d",
        side="long",
        features={
            "setup_score": setup_score,
            "context_score": context_score,
            "btc_return_1": 0.0,
            "eth_return_1": 0.0,
            "market_positive_return_fraction": 0.5,
            "risk_on_score_20": 0.5,
            "volatility_bucket_20": 1.0,
            "btc_trend_above_ma_20": 1.0,
            "eth_trend_above_ma_20": 0.0,
        },
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
    assert report.model_metadata["model_type"] == "multifeature_ridge"
    assert report.model_metadata["single_feature_model_type"] == "linear_probability_threshold"
    assert report.model_metadata["multifeature_model_type"] == "ridge_probability"
    assert report.model_metadata["training_target"] == "target_before_stop"
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
    assert report.model_metadata["validation_threshold_sweep"]
    assert any(row["selected"] for row in report.model_metadata["validation_threshold_sweep"])
    assert any(
        item["feature"] == "context_score" and item["model"] == "multifeature_ridge"
        for item in report.feature_importance
    )


def test_multifeature_ridge_reports_risk_controlled_primary_strategy() -> None:
    samples = [
        ModelSample(
            decision_time=_ts(1),
            symbol="BTCUSDT",
            timeframe="1d",
            side="long",
            features={"setup_score": 0.1, "context_score": 1.0},
            target_before_stop=True,
            realized_r_after_costs=1.0,
        ),
        ModelSample(
            decision_time=_ts(1),
            symbol="ETHUSDT",
            timeframe="1d",
            side="long",
            features={"setup_score": 0.2, "context_score": 0.8},
            target_before_stop=True,
            realized_r_after_costs=1.0,
        ),
        _multi_sample(2, setup_score=0.8, context_score=0.0, outcome_r=-1.0),
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
            max_trades_per_decision_time=1,
            max_trades_per_symbol=2,
            loss_cooldown_signals=1,
        ),
    )

    assert report.model_metadata["primary_strategy"] == "multifeature_ridge_risk_controlled_oos"
    assert report.model_metadata["risk_controls"] == {
        "max_trades_per_symbol": 2,
        "max_trades_per_decision_time": 1,
        "loss_cooldown_signals": 1,
    }
    assert "multifeature_ridge_risk_controlled_oos" in report.strategy_reports


def test_multifeature_ridge_reports_top_n_ranking_and_regime_slices() -> None:
    samples = [
        ModelSample(
            decision_time=_ts(1),
            symbol="BTCUSDT",
            timeframe="1d",
            side="long",
            features={
                "setup_score": 0.1,
                "context_score": 1.0,
                "btc_return_1": -0.002,
                "eth_return_1": -0.001,
                "market_positive_return_fraction": 0.2,
                "risk_on_score_20": 0.25,
                "volatility_bucket_20": 2.0,
                "btc_trend_above_ma_20": 0.0,
                "eth_trend_above_ma_20": 0.0,
            },
            target_before_stop=True,
            realized_r_after_costs=1.0,
        ),
        ModelSample(
            decision_time=_ts(1),
            symbol="ETHUSDT",
            timeframe="1d",
            side="long",
            features={
                "setup_score": 0.2,
                "context_score": 0.9,
                "btc_return_1": 0.002,
                "eth_return_1": 0.001,
                "market_positive_return_fraction": 0.8,
                "risk_on_score_20": 0.75,
                "volatility_bucket_20": 1.0,
                "btc_trend_above_ma_20": 1.0,
                "eth_trend_above_ma_20": 1.0,
            },
            target_before_stop=True,
            realized_r_after_costs=1.0,
        ),
        _multi_sample(2, setup_score=0.8, context_score=0.0, outcome_r=-1.0),
        _multi_sample(3, setup_score=0.2, context_score=1.0, outcome_r=1.0),
        _multi_sample(4, setup_score=0.8, context_score=0.0, outcome_r=-1.0),
        _multi_sample(5, setup_score=0.7, context_score=1.0, outcome_r=1.0),
        _multi_sample(6, setup_score=0.6, context_score=0.0, outcome_r=-1.0),
    ]

    report = train_and_evaluate_baselines(
        samples,
        BaselineConfig(
            feature_names=(
                "setup_score",
                "context_score",
                "btc_return_1",
                "eth_return_1",
                "market_positive_return_fraction",
                "risk_on_score_20",
                "volatility_bucket_20",
                "btc_trend_above_ma_20",
                "eth_trend_above_ma_20",
            ),
            decision_feature="setup_score",
            train_end=_ts(4),
            validation_end=_ts(5),
            test_end=_ts(6),
            probability_threshold_candidates=(0.4, 0.5, 0.6),
            ranking_top_n_values=(1, 2),
        ),
    )

    assert "multifeature_ridge_top1_oos" in report.strategy_reports
    assert "multifeature_ridge_top2_oos" in report.strategy_reports
    assert [row["strategy"] for row in report.model_metadata["ranking_comparison"]] == [
        "multifeature_ridge_top1_oos",
        "multifeature_ridge_top2_oos",
    ]
    regime = report.model_metadata["regime_stratification"]
    assert "btc_return_1_shock_band" in regime
    assert "risk_on_score_band" in regime
    assert "volatility_bucket" in regime
    assert any(row["bucket"] != "missing" for row in regime["btc_eth_trend_regime"])


def test_validation_threshold_calibration_ignores_zero_trade_thresholds() -> None:
    class ProbabilityFeatureModel:
        def probability(self, sample: ModelSample) -> float:
            return sample.features["probability"]

    result = _calibrate_probability_threshold(
        ProbabilityFeatureModel(),
        [
            ModelSample(
                decision_time=_ts(1),
                symbol="BTCUSDT",
                timeframe="1d",
                side="long",
                features={"probability": 0.5},
                target_before_stop=False,
                realized_r_after_costs=-1.0,
            ),
            ModelSample(
                decision_time=_ts(2),
                symbol="ETHUSDT",
                timeframe="1d",
                side="long",
                features={"probability": 0.5},
                target_before_stop=False,
                realized_r_after_costs=-1.0,
            ),
        ],
        BacktestConfig(initial_equity=10_000, risk_per_trade_pct=0.01),
        fallback=0.55,
        candidates=(0.4, 0.6),
    )

    assert result["selected_threshold"] == 0.4
    assert result["selected_source"] == "validation"
    assert [row["selected"] for row in result["sweep"]] == [True, False]


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
