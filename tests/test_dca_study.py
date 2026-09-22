"""Tests for the DCA execution-timing study.

The two properties that make this study meaningful are (1) every schedule
spends the same total, and (2) no schedule can see a price before it pays it.
Both are asserted here, plus the arithmetic that the report quotes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_trade_research.dca_study import metrics, schedules, study
from crypto_trade_research.dca_study.data import Series


def make_prices(days: int = 400, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2020-01-01", periods=days, freq="D")
    steps = rng.normal(0.001, 0.03, size=days)
    return pd.Series(100.0 * np.exp(np.cumsum(steps)), index=index, name="close")


def all_months(prices: pd.Series) -> list[pd.Period]:
    return study.campaign_months(prices)


@pytest.fixture
def prices() -> pd.Series:
    return make_prices()


def test_every_schedule_spends_the_same_total(prices):
    months = all_months(prices)
    monthly = 1000.0
    expected = monthly * len(months)

    built = {
        "fixed_1": schedules.fixed_day(prices, months, monthly, 1),
        "fixed_28": schedules.fixed_day(prices, months, monthly, 28),
        "weekly": schedules.weekly_split(prices, months, monthly),
        "daily": schedules.daily_split(prices, months, monthly),
        "pct90": schedules.weighted_split(
            prices, months, monthly, schedules.percentile_weights(prices, 90)
        ),
        "ma200": schedules.weighted_split(
            prices, months, monthly, schedules.ma_distance_weights(prices, 200)
        ),
    }
    dip, _ = schedules.dip_band(prices, months, monthly)
    built["dip"] = dip

    for name, spends in built.items():
        assert spends.sum() == pytest.approx(expected, rel=1e-9), name


def test_no_schedule_trades_outside_the_campaign_window(prices):
    months = all_months(prices)[2:6]
    monthly = 500.0
    window_start = pd.Period(months[0], freq="M").start_time
    window_end = pd.Period(months[-1], freq="M").end_time

    for spends in (
        schedules.daily_split(prices, months, monthly),
        schedules.weekly_split(prices, months, monthly),
        schedules.weighted_split(prices, months, monthly, schedules.percentile_weights(prices, 90)),
        schedules.dip_band(prices, months, monthly)[0],
    ):
        assert spends.index.min() >= window_start
        assert spends.index.max() <= window_end


def test_fixed_day_buys_once_per_month(prices):
    months = all_months(prices)
    spends = schedules.fixed_day(prices, months, 100.0, 15)
    assert len(spends) == len(months)
    assert set(spends.round(6)) == {100.0}


def test_fixed_day_falls_back_to_last_bar_of_a_short_month():
    index = pd.date_range("2021-02-01", "2021-02-28", freq="D")
    prices = pd.Series(np.arange(1.0, len(index) + 1), index=index)
    months = [pd.Period("2021-02", freq="M")]
    spends = schedules.fixed_day(prices, months, 100.0, 30)
    assert spends.index[0] == pd.Timestamp("2021-02-28")


def test_trailing_percentile_is_causal():
    """A change to a future price must not move a past percentile."""
    prices = make_prices(300)
    base = schedules.trailing_percentile(prices, 90)

    bumped = prices.copy()
    bumped.iloc[200:] *= 5.0
    after = schedules.trailing_percentile(bumped, 90)

    pd.testing.assert_series_equal(base.iloc[:200], after.iloc[:200])


def test_percentile_weights_are_bounded_and_inverted():
    rising = pd.Series(np.arange(1.0, 301.0), index=pd.date_range("2020-01-01", periods=300))
    weights = schedules.percentile_weights(rising, 90)
    tail = weights.iloc[120:]
    assert tail.min() >= schedules.MIN_WEIGHT - 1e-9
    assert tail.max() <= schedules.MAX_WEIGHT + 1e-9
    # A monotonically rising series always sits at the top of its own window.
    assert tail.max() == pytest.approx(schedules.MIN_WEIGHT)


def test_weighted_split_buys_more_when_cheap():
    """A V-shaped month must put more dollars near the bottom than the top."""
    index = pd.date_range("2020-01-01", periods=120, freq="D")
    values = np.concatenate([np.linspace(100, 50, 60), np.linspace(50, 100, 60)])
    prices = pd.Series(values, index=index)
    months = study.campaign_months(prices)
    weights = schedules.percentile_weights(prices, 30)
    spends = schedules.weighted_split(prices, months, 1000.0, weights)

    paid = prices.reindex(spends.index)
    cheap = spends[paid < 70].sum()
    rich = spends[paid > 90].sum()
    assert cheap > rich


def test_even_daily_split_reaches_the_harmonic_mean(prices):
    months = all_months(prices)[:6]
    window = prices.index[pd.PeriodIndex(prices.index, freq="M").isin(months)]
    spends = schedules.daily_split(prices, months, 1000.0)
    result = metrics.evaluate("TEST", "daily", prices, spends, window)
    # Equal dollars per day within each month; months are near-equal length, so
    # the achieved basis must sit essentially on the harmonic mean, and below
    # the arithmetic mean.
    assert result.cost_basis < result.mean_price
    assert result.basis_vs_harmonic_pct == pytest.approx(0.0, abs=0.35)


def test_dip_band_diagnostics_and_forced_deployment():
    """A series that never dips must still deploy everything, by timeout."""
    index = pd.date_range("2020-01-01", periods=730, freq="D")
    prices = pd.Series(np.linspace(100, 400, len(index)), index=index)
    months = study.campaign_months(prices)
    spends, diagnostics = schedules.dip_band(prices, months, 1000.0, drawdown=0.20)
    assert spends.sum() == pytest.approx(1000.0 * len(months))
    assert diagnostics["share_deployed_on_dip"] == pytest.approx(0.0)
    assert diagnostics["share_deployed_by_timeout"] == pytest.approx(1.0)
    assert diagnostics["mean_cash_held_months"] > 1.0


def test_bootstrap_ci_widens_with_autocorrelated_input():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, 400)
    correlated = pd.Series(noise).rolling(30, min_periods=1).mean().to_numpy()
    _, low_i, high_i = metrics.moving_block_bootstrap_ci(correlated, block=1)
    _, low_b, high_b = metrics.moving_block_bootstrap_ci(correlated, block=24)
    assert (high_b - low_b) > (high_i - low_i)


def test_run_symbol_produces_one_row_per_schedule_and_start():
    prices = make_prices(900)
    series = Series("TESTUSDT", prices.to_frame("close"))
    specs = study.default_specs(fixed_days=(1, 15))
    campaigns, diagnostics = study.run_symbol(series, length_months=12, specs=specs)

    starts = campaigns["start_month"].nunique()
    assert len(campaigns) == starts * len(specs)
    assert set(campaigns["schedule"]) == {s.name for s in specs}
    assert not diagnostics.empty

    summary = study.summarise(campaigns, "fixed_day_01")
    row = summary[summary["schedule"] == "fixed_day_01"].iloc[0]
    assert row["basis_vs_baseline_pct"] == pytest.approx(0.0, abs=1e-9)


def test_mean_fixed_day_baseline_centres_the_fixed_days():
    """Against the all-days average, the 28 fixed days must straddle zero."""
    prices = make_prices(1500)
    series = Series("TESTUSDT", prices.to_frame("close"))
    campaigns, _ = study.run_symbol(series, length_months=12)
    summary = study.summarise(campaigns, study.MEAN_FIXED_DAY)
    fixed = summary[summary["schedule"].str.startswith("fixed_day_")]
    assert (fixed["basis_vs_baseline_pct"] < 0).any()
    assert (fixed["basis_vs_baseline_pct"] > 0).any()
    assert abs(fixed["basis_vs_baseline_pct"].mean()) < 0.05


def test_day_of_month_stability_reports_both_halves():
    prices = make_prices(2000)
    series = Series("TESTUSDT", prices.to_frame("close"))
    campaigns, _ = study.run_symbol(series, length_months=12)
    stability = study.day_of_month_stability(campaigns)
    assert stability["days"] == 28
    assert -1.0 <= stability["spearman"] <= 1.0
    assert 1 <= stability["first_half_best_day"] <= 28


def test_intramonth_bias_is_zero_for_a_flat_series():
    index = pd.date_range("2020-01-01", periods=365, freq="D")
    flat = pd.Series(100.0, index=index)
    bias = study.monthly_intramonth_bias(flat, 15)
    assert np.allclose(bias.to_numpy(), 0.0)
