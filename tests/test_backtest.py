from datetime import UTC, datetime

import pytest

from crypto_trade_research.backtest.walk_forward import (
    BacktestConfig,
    SignalRow,
    evaluate_signal_strategy,
    walk_forward_splits,
)


def _ts(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=UTC)


def _signal(
    day: int,
    side: str,
    gross_r: float,
    confidence: float = 1.0,
    exit_day: int | None = None,
) -> SignalRow:
    return SignalRow(
        decision_time=_ts(day),
        exit_time=_ts(exit_day) if exit_day else None,
        symbol="BTCUSDT",
        timeframe="1d",
        side=side,
        gross_r=gross_r,
        confidence=confidence,
    )


def test_evaluate_signal_strategy_produces_known_trades_and_metrics() -> None:
    report = evaluate_signal_strategy(
        strategy_name="known_path",
        signals=[
            _signal(1, "long", 2.0),
            _signal(2, "short", -1.0),
            _signal(3, "flat", 0.0),
            _signal(4, "long", 0.5),
        ],
        config=BacktestConfig(
            initial_equity=10_000,
            risk_per_trade_pct=0.01,
            fee_r=0.05,
            spread_r=0.02,
            slippage_r=0.03,
        ),
    )

    assert len(report.trades) == 3
    assert [trade.net_r for trade in report.trades] == pytest.approx([1.9, -1.1, 0.4])
    assert report.metrics.trade_count == 3
    assert report.metrics.win_rate == pytest.approx(2 / 3)
    assert report.metrics.average_r == pytest.approx(0.4)
    assert report.metrics.profit_factor == pytest.approx(2.3 / 1.1)
    assert report.metrics.total_return_pct == pytest.approx(0.011822164)
    assert report.metrics.max_drawdown_pct == pytest.approx(0.011)
    assert report.equity_curve[-1].equity == pytest.approx(10118.22164)


def test_costs_can_turn_gross_profitable_strategy_net_unprofitable() -> None:
    low_cost = evaluate_signal_strategy(
        "low_cost",
        [_signal(1, "long", 0.2), _signal(2, "long", 0.2)],
        BacktestConfig(initial_equity=10_000, risk_per_trade_pct=0.01, fee_r=0.01),
    )
    high_cost = evaluate_signal_strategy(
        "high_cost",
        [_signal(1, "long", 0.2), _signal(2, "long", 0.2)],
        BacktestConfig(initial_equity=10_000, risk_per_trade_pct=0.01, fee_r=0.25),
    )

    assert low_cost.metrics.average_r > 0
    assert high_cost.metrics.average_r < 0


def test_backtest_tracks_duration_aware_concurrent_exposure() -> None:
    report = evaluate_signal_strategy(
        "overlap",
        [
            _signal(1, "long", 1.0, exit_day=3),
            _signal(2, "long", 1.0, exit_day=4),
            _signal(4, "long", 1.0, exit_day=5),
        ],
        BacktestConfig(initial_equity=10_000, risk_per_trade_pct=0.01),
    )

    assert [trade.exit_time for trade in report.trades] == [_ts(3), _ts(4), _ts(5)]
    assert report.metrics.max_concurrent_positions == 2
    assert report.metrics.max_concurrent_risk_pct == pytest.approx(0.02)
    assert report.to_report_dict()["metrics"]["max_concurrent_positions"] == 2


def test_walk_forward_splits_are_time_ordered_and_compare_strategies() -> None:
    timestamps = [_ts(day) for day in range(1, 9)]
    splits = walk_forward_splits(
        timestamps,
        train_size=3,
        validation_size=2,
        test_size=1,
        step_size=1,
        anchored=False,
    )

    assert len(splits) == 3
    assert splits[0].train_start == _ts(1)
    assert splits[0].train_end == _ts(3)
    assert splits[0].validation_start == _ts(4)
    assert splits[0].test_start == _ts(6)
    assert splits[1].train_start == _ts(2)

    momentum = evaluate_signal_strategy(
        "momentum",
        [_signal(1, "long", 1.0), _signal(2, "long", -0.5), _signal(3, "long", 1.0)],
        BacktestConfig(initial_equity=10_000, risk_per_trade_pct=0.01, fee_r=0.05),
    )
    mean_reversion = evaluate_signal_strategy(
        "mean_reversion",
        [_signal(1, "short", -0.2), _signal(2, "short", -0.2), _signal(3, "short", -0.2)],
        BacktestConfig(initial_equity=10_000, risk_per_trade_pct=0.01, fee_r=0.05),
    )

    assert momentum.metrics.average_r > mean_reversion.metrics.average_r
    assert momentum.to_report_dict()["metrics"]["trade_count"] == 3
