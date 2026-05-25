from datetime import UTC, datetime

from crypto_trade_research.meta_strategy import (
    CandidateSetup,
    MetaStrategyConfig,
    ModelEstimate,
    candidate_key,
    evaluate_meta_strategy,
    generate_trend_pullback_candidates,
    select_threshold_on_validation,
)


def _ts(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def _feature_row(
    day: int,
    close: float,
    ma: float,
    return_1: float,
    range_position: float,
) -> dict[str, object]:
    return {
        "decision_time": _ts(day),
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "close": close,
        "ma_3": ma,
        "ma_slope_3": 0.01,
        "return_1": return_1,
        "range_position_3": range_position,
        "volatility_expansion_3": 1.0,
    }


def test_generate_trend_pullback_candidates_is_deterministic() -> None:
    candidates = generate_trend_pullback_candidates(
        [
            _feature_row(1, 101, 100, 0.02, 0.8),
            _feature_row(2, 102, 100, -0.01, 0.45),
            _feature_row(3, 99, 100, -0.02, 0.2),
        ],
        pullback_return_threshold=-0.005,
        max_range_position=0.6,
    )

    assert candidates == [
        CandidateSetup(
            decision_time=_ts(2),
            symbol="BTCUSDT",
            timeframe="1d",
            setup_type="trend_pullback_continuation",
            side="long",
            deterministic_score=0.55,
            rule_only_gross_r=1.0,
        )
    ]


def test_meta_strategy_filter_improves_selectivity_and_records_rejections() -> None:
    candidates = [
        CandidateSetup(_ts(1), "BTCUSDT", "1d", "trend_pullback_continuation", "long", 0.8, 1.0),
        CandidateSetup(_ts(2), "BTCUSDT", "1d", "trend_pullback_continuation", "long", 0.7, -1.0),
        CandidateSetup(_ts(3), "BTCUSDT", "1d", "trend_pullback_continuation", "long", 0.9, 1.5),
    ]
    estimates = {
        candidate_key(candidates[0]): ModelEstimate(
            probability_target_before_stop=0.7,
            expected_r=0.8,
            stopout_risk=0.2,
        ),
        candidate_key(candidates[1]): ModelEstimate(
            probability_target_before_stop=0.45,
            expected_r=-0.2,
            stopout_risk=0.7,
        ),
        candidate_key(candidates[2]): ModelEstimate(
            probability_target_before_stop=0.8,
            expected_r=1.0,
            stopout_risk=0.1,
        ),
    }

    report = evaluate_meta_strategy(
        candidates,
        estimates,
        MetaStrategyConfig(
            probability_threshold=0.6,
            expected_r_threshold=0.2,
            max_stopout_risk=0.5,
            max_symbol_exposure=0.02,
            risk_per_trade_pct=0.01,
        ),
    )

    assert report.rule_only.metrics.trade_count == 3
    assert report.ml_filtered.metrics.trade_count == 2
    assert report.ml_filtered.metrics.average_r > report.rule_only.metrics.average_r
    assert report.rejected_trades[0].reason == "probability_below_threshold"
    assert report.rejected_trades[0].decision_time == _ts(2)
    assert report.to_report_dict()["rejected_trade_count"] == 1


def test_threshold_selected_on_validation_then_reported_on_untouched_test() -> None:
    validation_candidates = [
        CandidateSetup(_ts(1), "BTCUSDT", "1d", "trend_pullback_continuation", "long", 0.8, 1.0),
        CandidateSetup(_ts(2), "BTCUSDT", "1d", "trend_pullback_continuation", "long", 0.7, -1.0),
        CandidateSetup(_ts(3), "BTCUSDT", "1d", "trend_pullback_continuation", "long", 0.9, 1.0),
    ]
    validation_estimates = {
        candidate_key(validation_candidates[0]): ModelEstimate(0.55, 0.5, 0.2),
        candidate_key(validation_candidates[1]): ModelEstimate(0.65, 0.5, 0.2),
        candidate_key(validation_candidates[2]): ModelEstimate(0.75, 0.5, 0.2),
    }

    selected = select_threshold_on_validation(
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

    assert selected.probability_threshold == 0.7

    test_candidates = [
        CandidateSetup(
            _ts(4),
            "BTCUSDT",
            "1d",
            "trend_pullback_continuation",
            "long",
            0.8,
            1.0,
        ),
        CandidateSetup(
            _ts(5),
            "BTCUSDT",
            "1d",
            "trend_pullback_continuation",
            "long",
            0.8,
            -1.0,
        ),
    ]
    test_report = evaluate_meta_strategy(
        test_candidates,
        {
            candidate_key(test_candidates[0]): ModelEstimate(0.72, 0.4, 0.2),
            candidate_key(test_candidates[1]): ModelEstimate(0.62, 0.4, 0.2),
        },
        selected,
    )

    assert test_report.ml_filtered.metrics.trade_count == 1
    assert test_report.selected_threshold_source == "validation"


def test_estimates_are_keyed_by_full_candidate_identity() -> None:
    same_time = _ts(1)
    candidates = [
        CandidateSetup(
            same_time,
            "BTCUSDT",
            "1d",
            "trend_pullback_continuation",
            "long",
            0.8,
            1.0,
        ),
        CandidateSetup(
            same_time,
            "ETHUSDT",
            "1d",
            "trend_pullback_continuation",
            "long",
            0.8,
            1.0,
        ),
    ]
    estimates = {
        candidate_key(candidates[0]): ModelEstimate(0.8, 0.6, 0.2),
        candidate_key(candidates[1]): ModelEstimate(0.4, 0.6, 0.2),
    }

    report = evaluate_meta_strategy(
        candidates,
        estimates,
        MetaStrategyConfig(
            probability_threshold=0.6,
            expected_r_threshold=0.1,
            max_stopout_risk=0.5,
            max_symbol_exposure=0.02,
            risk_per_trade_pct=0.01,
        ),
    )

    assert report.ml_filtered.metrics.trade_count == 1
    assert report.rejected_trades[0].symbol == "ETHUSDT"
