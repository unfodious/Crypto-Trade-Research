"""Leakage guarantees for the edge study.

The mandatory test here is `test_future_bars_cannot_change_past_features`: it
corrupts every bar after a cut point and asserts that not one feature value at
or before the cut point moves. Any centred window, any full-series scaler, any
forward-looking merge would fail it. It runs over every grid the study joins -
4h, 1d, BTC context, and the three non-price panels (funding, open interest,
book depth) - because a feature without a leakage assertion is not done.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crypto_trade_research.edge_study import altdata as ad
from crypto_trade_research.edge_study import cross_section as cs
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


def synthetic_alt_panels(
    pair: str = "TESTUSDT",
    days: int = 160,
    seed: int = 21,
) -> ad.AltPanels:
    """Funding / metrics / depth panels on their own clocks, with `known_at`.

    Shapes and column names match what `altdata` writes from the real archives,
    so a test that corrupts these is corrupting exactly what the study reads.
    """
    rng = np.random.default_rng(seed)
    funding_time = pd.date_range("2024-07-01", periods=days * 3, freq="8h", tz="UTC")
    funding = pd.DataFrame(
        {
            "funding_time": funding_time,
            "funding_rate": rng.normal(0.0001, 0.0002, size=len(funding_time)),
        }
    )
    funding["known_at"] = funding["funding_time"] + ad.FUNDING_LAG

    metrics_time = pd.date_range("2024-07-01", periods=days * 288, freq="5min", tz="UTC")
    count = len(metrics_time)
    open_interest = 1e6 * np.exp(np.cumsum(rng.normal(0.0, 0.0005, size=count)))
    metrics = pd.DataFrame(
        {
            "metrics_time": metrics_time,
            "sum_open_interest": open_interest,
            "sum_open_interest_value": open_interest * 100.0,
            "count_toptrader_long_short_ratio": rng.uniform(0.5, 3.0, size=count),
            "sum_toptrader_long_short_ratio": rng.uniform(0.5, 3.0, size=count),
            "count_long_short_ratio": rng.uniform(0.5, 3.0, size=count),
            "sum_taker_long_short_vol_ratio": rng.uniform(0.3, 2.0, size=count),
        }
    )
    metrics["known_at"] = metrics["metrics_time"] + ad.METRICS_LAG

    depth_time = metrics_time
    depth = pd.DataFrame({"depth_time": depth_time})
    for level in ad.DEPTH_LEVELS:
        scale = 1e5 * level
        depth[f"bid_notional_{level}pct"] = scale * rng.uniform(0.8, 1.2, size=count)
        depth[f"ask_notional_{level}pct"] = scale * rng.uniform(0.8, 1.2, size=count)
    depth["known_at"] = depth["depth_time"] + ad.DEPTH_LAG

    return ad.AltPanels(pair=pair, funding=funding, metrics=metrics, depth=depth)


def _corrupt_after(frame: pd.DataFrame, cut: pd.Timestamp, factor: float = 3.5) -> pd.DataFrame:
    """Multiply every numeric value stamped after `cut` by `factor`."""
    corrupted = frame.copy()
    mask = corrupted["known_at"] > cut
    numeric = [
        column
        for column in corrupted.columns
        if column not in {"known_at"}
        and not pd.api.types.is_datetime64_any_dtype(corrupted[column])
    ]
    corrupted.loc[mask, numeric] = corrupted.loc[mask, numeric] * factor
    return corrupted


def _numeric(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [c for c in feat.FEATURE_COLUMNS if c in frame.columns]
    return frame[columns].astype(float)


def test_future_bars_cannot_change_past_features():
    """The load-bearing test: corrupt the future on EVERY grid, past must not move.

    Grids corrupted simultaneously: 4h bars, 1d bars, BTC 1d context, and the
    funding, open-interest and book-depth panels. If any new feature reached
    forward - a centred window, a full-series statistic, a `merge_asof` with
    `direction="forward"`, a publication lag applied in the wrong direction -
    one of the 55 columns would move here.
    """
    bars_4h = synthetic_bars(900, "4h")
    bars_1d = synthetic_bars(160, "1D", seed=11)
    btc_1d = synthetic_bars(160, "1D", seed=13)
    panels = synthetic_alt_panels(days=160)

    original = feat.build_features(bars_4h, bars_1d, btc_1d, panels)
    # The cut is the same instant on every grid: 600 4h bars == 100 days.
    cut = 600
    daily_cut = cut // 6
    cut_time = original["decision_time"].iloc[cut - 1]

    corrupted_4h = bars_4h.copy()
    corrupted_4h.iloc[cut:] *= 3.5
    corrupted_1d = bars_1d.copy()
    corrupted_1d.iloc[daily_cut:] *= 3.5
    corrupted_btc = btc_1d.copy()
    corrupted_btc.iloc[daily_cut:] *= 3.5
    corrupted_panels = ad.AltPanels(
        pair=panels.pair,
        funding=_corrupt_after(panels.funding, cut_time),
        metrics=_corrupt_after(panels.metrics, cut_time),
        depth=_corrupt_after(panels.depth, cut_time),
    )

    shifted = feat.build_features(corrupted_4h, corrupted_1d, corrupted_btc, corrupted_panels)

    # The alt columns must actually be populated, or this test asserts nothing.
    assert original[list(feat.ALT_FEATURE_COLUMNS)].notna().any().all()

    left = _numeric(original.iloc[:cut])
    right = _numeric(shifted.iloc[:cut])
    pd.testing.assert_frame_equal(left, right, check_exact=False, atol=1e-12)


def test_truncating_alt_panels_does_not_change_earlier_features():
    """The same claim from the other side, for the non-price grids."""
    bars_4h = synthetic_bars(700, "4h")
    bars_1d = synthetic_bars(120, "1D", seed=11)
    panels = synthetic_alt_panels(days=120)
    full = feat.build_features(bars_4h, bars_1d, None, panels)

    horizon = full["decision_time"].iloc[399]
    truncated_panels = ad.AltPanels(
        pair=panels.pair,
        funding=panels.funding[panels.funding["known_at"] <= horizon],
        metrics=panels.metrics[panels.metrics["known_at"] <= horizon],
        depth=panels.depth[panels.depth["known_at"] <= horizon],
    )
    truncated = feat.build_features(bars_4h, bars_1d, None, truncated_panels)
    alt = list(feat.ALT_FEATURE_COLUMNS)
    pd.testing.assert_frame_equal(
        full[alt].iloc[:400].astype(float),
        truncated[alt].iloc[:400].astype(float),
        check_exact=False,
        atol=1e-12,
    )


def test_alt_panel_values_are_invisible_before_their_known_at():
    """A row stamped at `known_at` may not influence any earlier decision row.

    Spiking one panel row and checking that only decision rows at or after its
    `known_at` change is the direct statement of the publication-lag contract:
    funding at its settlement, OI at snapshot + 5m, depth at snapshot + 1m.
    """
    bars_4h = synthetic_bars(600, "4h")
    bars_1d = synthetic_bars(100, "1D", seed=11)
    panels = synthetic_alt_panels(days=100)
    base = feat.build_features(bars_4h, bars_1d, None, panels)

    cases = [
        ("funding", "funding_rate", ad.FUNDING_LAG, feat.ALT_FEATURE_COLUMNS[:4]),
        ("metrics", "sum_open_interest", ad.METRICS_LAG, ("oi_change_4h", "oi_change_1d")),
        ("depth", "bid_notional_1pct", ad.DEPTH_LAG, ("depth_imbalance_1pct",)),
    ]
    for panel_name, column, lag, watched in cases:
        panel = getattr(panels, panel_name).copy()
        position = len(panel) // 2
        native_time = panel["known_at"].iloc[position] - lag
        panel.loc[panel.index[position], column] = panel[column].iloc[position] * 50.0
        spiked = feat.build_features(
            bars_4h,
            bars_1d,
            None,
            ad.AltPanels(
                pair=panels.pair,
                funding=panel if panel_name == "funding" else panels.funding,
                metrics=panel if panel_name == "metrics" else panels.metrics,
                depth=panel if panel_name == "depth" else panels.depth,
            ),
        )
        watched_columns = list(watched)
        changed = (base[watched_columns] - spiked[watched_columns]).abs().max(axis=1).fillna(
            0.0
        ) > 1e-12
        if not changed.any():
            continue
        first_changed = base.loc[changed, "decision_time"].min()
        assert first_changed >= native_time + lag, (
            f"{panel_name}.{column} moved a feature at {first_changed}, "
            f"before its known_at {native_time + lag}"
        )


def test_liquidations_are_declared_as_a_proxy_not_a_feed():
    """The proxy must stay named as a proxy and must stay derived, not fetched.

    Binance retired the historical `liquidationSnapshot` archive; the only
    in-repo liquidation source is a live websocket recorder. If someone later
    wires a real feed in, this test should be deleted deliberately rather than
    a proxy quietly being presented as liquidation data.
    """
    assert ad.LIQUIDATION_PROXY_FEATURES == ("liq_pressure_long", "liq_pressure_short")
    assert all(name.startswith("liq_pressure") for name in ad.LIQUIDATION_PROXY_FEATURES)
    assert "proxy" in ad.__doc__.lower()
    assert not hasattr(ad, "fetch_liquidations")


def test_cross_sectional_ranks_use_only_same_instant_rows():
    """A within-bar rank must be a function of that bar's rows and nothing else."""
    times = pd.to_datetime(["2024-07-01T04:00Z"] * 4 + ["2024-07-01T08:00Z"] * 4)
    frame = pd.DataFrame(
        {
            "decision_time": times,
            "pair": ["A", "B", "C", "D"] * 2,
            "rsi": [10.0, 20.0, 30.0, 40.0, 5.0, 6.0, 7.0, 8.0],
        }
    )
    ranked = cs.cross_sectional_ranks(frame, ["rsi"])
    first = ranked[ranked["decision_time"] == times[0]]["cs_rsi"].to_numpy()
    second = ranked[ranked["decision_time"] == times[4]]["cs_rsi"].to_numpy()
    # Identical orderings at two instants with wildly different levels must give
    # identical ranks: the market factor is gone, only the ordering survives.
    assert np.allclose(first, second)

    moved = frame.copy()
    moved.loc[7, "rsi"] = 1000.0  # change the LATER bar only
    removed = cs.cross_sectional_ranks(moved, ["rsi"])
    assert np.allclose(removed[removed["decision_time"] == times[0]]["cs_rsi"].to_numpy(), first)


def test_relative_label_compares_only_pairs_quoted_at_the_same_instant():
    times = pd.to_datetime(["2024-07-01T04:00Z"] * 6 + ["2024-07-01T08:00Z"] * 6)
    longs = pd.DataFrame(
        {
            "decision_time": times,
            "pair": [f"P{i}" for i in range(6)] * 2,
            "gross_r": [-1.0, -1.0, -1.0, 2.0, 2.0, 2.0, 5.0, 5.0, 5.0, 6.0, 6.0, 6.0],
            "mfe_r": 0.0,
            "win": 0,
        }
    )
    labelled = cs.relative_labels(longs, min_pairs=6)
    first = labelled[labelled["decision_time"] == times[0]]
    second = labelled[labelled["decision_time"] == times[6]]
    # A +2.0 R pair wins in the first bar and a +5.0 R pair loses in the second:
    # the label is relative, so an absolute return cannot decide it.
    assert first.sort_values("pair")["win"].tolist() == [0, 0, 0, 1, 1, 1]
    assert second.sort_values("pair")["win"].tolist() == [0, 0, 0, 1, 1, 1]


def test_relative_label_breaks_stop_out_ties_on_mfe():
    """All six pairs stop out; the label must still split them, not collapse.

    A plain "above the median realized R" label gives every row 0 here, which
    is exactly the degeneracy MFE tie-breaking exists to remove.
    """
    times = pd.to_datetime(["2024-07-01T04:00Z"] * 6)
    longs = pd.DataFrame(
        {
            "decision_time": times,
            "pair": [f"P{i}" for i in range(6)],
            "gross_r": [-1.0] * 6,
            "mfe_r": [0.1, 0.2, 0.3, 1.0, 1.1, 1.2],
            "win": 0,
        }
    )
    labelled = cs.relative_labels(longs, min_pairs=6)
    assert labelled.sort_values("pair")["win"].tolist() == [0, 0, 0, 1, 1, 1]


def test_thin_cross_sections_are_dropped():
    times = pd.to_datetime(["2024-07-01T04:00Z"] * 3)
    longs = pd.DataFrame(
        {
            "decision_time": times,
            "pair": list("ABC"),
            "gross_r": [1.0, 2.0, 3.0],
            "mfe_r": 0.0,
            "win": 0,
        }
    )
    assert cs.relative_labels(longs, min_pairs=6).empty


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
