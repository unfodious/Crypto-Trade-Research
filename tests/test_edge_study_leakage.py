"""Leakage guarantees for the edge study.

The mandatory test here is `test_future_bars_cannot_change_past_features`: it
corrupts every bar after a cut point and asserts that not one feature value at
or before the cut point moves. Any centred window, any full-series scaler, any
forward-looking merge would fail it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_trade_research.edge_study import features as feat
from crypto_trade_research.edge_study import indicators as ind
from crypto_trade_research.edge_study import labels as lab
from crypto_trade_research.edge_study import setups as setup_rules
from crypto_trade_research.edge_study.walkforward import WalkForwardConfig, run_walk_forward


def synthetic_bars(periods: int, freq: str, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-07-01", periods=periods, freq=freq, tz="UTC")
    steps = rng.normal(0.0, 0.01, size=periods)
    close = 100.0 * np.exp(np.cumsum(steps))
    spread = np.abs(rng.normal(0.0, 0.004, size=periods)) * close
    open_price = np.concatenate([[close[0]], close[:-1]])
    volume = rng.uniform(100.0, 1000.0, size=periods)
    return pd.DataFrame(
        {
            "open": open_price,
            "high": np.maximum(open_price, close) + spread,
            "low": np.minimum(open_price, close) - spread,
            "close": close,
            "volume": volume,
            "quote_volume": volume * close,
            "count": rng.integers(50, 500, size=periods).astype(float),
            "taker_buy_quote_volume": volume * close * rng.uniform(0.3, 0.7, size=periods),
        },
        index=index,
    )


def _numeric(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [c for c in feat.FEATURE_COLUMNS if c in frame.columns]
    return frame[columns].astype(float)


def test_future_bars_cannot_change_past_features():
    bars_4h = synthetic_bars(900, "4h")
    bars_1d = synthetic_bars(160, "1D", seed=11)
    btc_1d = synthetic_bars(160, "1D", seed=13)

    original = feat.build_features(bars_4h, bars_1d, btc_1d)
    # The cut is the same instant on both grids: 600 4h bars == 100 days.
    cut = 600
    daily_cut = cut // 6

    corrupted_4h = bars_4h.copy()
    corrupted_4h.iloc[cut:] *= 3.5
    corrupted_1d = bars_1d.copy()
    corrupted_1d.iloc[daily_cut:] *= 3.5
    corrupted_btc = btc_1d.copy()
    corrupted_btc.iloc[daily_cut:] *= 3.5

    shifted = feat.build_features(corrupted_4h, corrupted_1d, corrupted_btc)

    left = _numeric(original.iloc[:cut])
    right = _numeric(shifted.iloc[:cut])
    pd.testing.assert_frame_equal(left, right, check_exact=False, atol=1e-12)


def test_truncating_the_series_does_not_change_earlier_features():
    bars_4h = synthetic_bars(700, "4h")
    bars_1d = synthetic_bars(120, "1D", seed=11)
    full = feat.build_features(bars_4h, bars_1d, None)
    truncated = feat.build_features(bars_4h.iloc[:498], bars_1d.iloc[:83], None)
    horizon = truncated.index[-1]
    pd.testing.assert_frame_equal(
        _numeric(full.loc[full.index <= horizon]),
        _numeric(truncated),
        check_exact=False,
        atol=1e-12,
    )


def test_daily_context_uses_only_closed_daily_bars():
    bars_4h = synthetic_bars(300, "4h")
    bars_1d = synthetic_bars(60, "1D", seed=5)
    frame = feat.build_features(bars_4h, bars_1d, None)
    daily = feat.base_frame(bars_1d, "1D")
    joined = frame.dropna(subset=["d1_rsi"])
    for row in joined.itertuples():
        matches = daily[np.isclose(daily["rsi"], row.d1_rsi, equal_nan=False)]
        assert (matches["decision_time"] <= row.decision_time).any()


def test_decision_time_is_the_bar_close_not_the_bar_open():
    bars_4h = synthetic_bars(50, "4h")
    frame = feat.base_frame(bars_4h, "4h")
    assert (frame["decision_time"] - frame.index == pd.Timedelta(hours=4)).all()


def test_donchian_channel_excludes_the_current_bar():
    high = pd.Series([1.0, 2.0, 3.0, 10.0, 4.0])
    low = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
    channel_high, _ = ind.donchian(high, low, 3)
    assert channel_high.iloc[3] == 3.0  # the 10.0 bar cannot see its own high
    assert channel_high.iloc[4] == 10.0


def test_walk_forward_training_never_overlaps_the_test_window():
    rng = np.random.default_rng(1)
    count = 2000
    times = pd.date_range("2024-07-01", periods=count, freq="4h", tz="UTC")
    samples = pd.DataFrame(
        {
            "decision_time": times,
            "exit_time": times + pd.Timedelta(days=5),
            "win": rng.integers(0, 2, size=count),
        }
    )
    for name in ("f0", "f1"):
        samples[name] = rng.normal(size=count)

    config = WalkForwardConfig(folds=4, embargo_days=7.0, min_train=100, selectivity=0.5)
    predictions, folds = run_walk_forward(samples, ["f0", "f1"], config)
    assert folds
    embargo = pd.Timedelta(days=config.embargo_days)
    for fold in folds:
        train = samples[samples["exit_time"] < fold.test_start - embargo]
        assert train["exit_time"].max() < fold.test_start - embargo
        assert fold.train_size == len(train)
    # Every test row is predicted exactly once, by one fold only.
    assert predictions["decision_time"].is_unique


@pytest.mark.parametrize(
    ("path", "side", "expected"),
    [
        ([(101.0, 100.0), (103.0, 102.0)], 1, lab.TARGET),
        ([(100.5, 99.0), (100.0, 98.0)], 1, lab.STOP),
        ([(103.0, 98.0)], 1, lab.STOP),  # both barriers in one minute -> stop
        ([(100.2, 99.9), (100.3, 99.8)], 1, lab.TIMEOUT),
        ([(100.0, 97.0)], -1, lab.TARGET),
        ([(102.0, 100.0)], -1, lab.STOP),
    ],
)
def test_barrier_resolution_order(path, side, expected):
    index = pd.date_range("2024-07-01", periods=len(path) + 1, freq="1min", tz="UTC")
    minute = pd.DataFrame(
        {
            "high": [100.0, *[p[0] for p in path]],
            "low": [100.0, *[p[1] for p in path]],
            "close": [100.0, *[p[0] for p in path]],
        },
        index=index,
    )
    stop, target = lab.barrier_prices(
        100.0, side, 1.0, lab.BarrierConfig(stop_atr=1.0, target_atr=2.0)
    )
    setups = pd.DataFrame(
        {
            "decision_time": [index[0]],
            "side": [side],
            "entry_price": [100.0],
            "stop_price": [stop],
            "target_price": [target],
        }
    )
    labelled = lab.label_setups(setups, minute, lab.BarrierConfig(horizon_bars=1, bar_hours=1.0))
    assert labelled.iloc[0]["barrier"] == expected


def test_labels_never_look_beyond_the_horizon():
    index = pd.date_range("2024-07-01", periods=400, freq="1min", tz="UTC")
    high = np.full(400, 100.2)
    low = np.full(400, 99.8)
    high[300] = 200.0  # far outside a 1-bar (60 minute) horizon
    minute = pd.DataFrame({"high": high, "low": low, "close": np.full(400, 100.0)}, index=index)
    config = lab.BarrierConfig(stop_atr=1.0, target_atr=2.0, horizon_bars=1, bar_hours=1.0)
    stop, target = lab.barrier_prices(100.0, 1, 1.0, config)
    setups = pd.DataFrame(
        {
            "decision_time": [index[0]],
            "side": [1],
            "entry_price": [100.0],
            "stop_price": [stop],
            "target_price": [target],
        }
    )
    labelled = lab.label_setups(setups, minute, config)
    assert labelled.iloc[0]["barrier"] == lab.TIMEOUT


def test_setups_only_fire_on_closed_channel_breaks():
    bars_4h = synthetic_bars(400, "4h")
    bars_1d = synthetic_bars(70, "1D", seed=2)
    frame = feat.build_features(bars_4h, bars_1d, None)
    candidates = setup_rules.generate_setups(frame, lab.BarrierConfig())
    assert not candidates.empty
    breakouts = candidates[candidates["family"] == setup_rules.BREAKOUT]
    for row in breakouts.itertuples():
        reference = frame.loc[row.bar_time]
        if row.side > 0:
            assert reference["close"] > reference["donchian_high"]
        else:
            assert reference["close"] < reference["donchian_low"]
        assert row.decision_time == row.bar_time + pd.Timedelta(hours=4)
