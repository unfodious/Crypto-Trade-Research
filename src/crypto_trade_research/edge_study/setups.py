"""Candidate setup generation.

The gradient-boosting model in this study is a FILTER, not an entry generator:
the rules below decide WHERE a trade could be taken, the model only decides
WHETHER to take it. Keeping entry generation in plain, inspectable rules is what
makes the "does the model beat random entry with the same geometry" comparison
meaningful.

Two families, both long and short, both evaluated on the 4h grid:

- `breakout`  : close beyond the 20-bar Donchian channel (trend continuation).
- `reversion` : RSI(14) below 30 / above 70 (stretch back toward the mean).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_trade_research.edge_study.labels import BarrierConfig, barrier_prices

BREAKOUT = "breakout"
REVERSION = "reversion"


def _rows(
    frame: pd.DataFrame,
    mask: pd.Series,
    side: int,
    family: str,
    config: BarrierConfig,
) -> pd.DataFrame:
    selected = frame[mask & frame["atr"].notna() & (frame["atr"] > 0)]
    if selected.empty:
        return pd.DataFrame()
    entry = selected["close"].to_numpy(dtype=float)
    atr_values = selected["atr"].to_numpy(dtype=float)
    stops, targets = zip(
        *(barrier_prices(e, side, a, config) for e, a in zip(entry, atr_values, strict=True)),
        strict=True,
    )
    return pd.DataFrame(
        {
            "decision_time": selected["decision_time"].to_numpy(),
            "bar_time": selected.index,
            "side": side,
            "family": family,
            "entry_price": entry,
            "atr": atr_values,
            "stop_price": np.asarray(stops, dtype=float),
            "target_price": np.asarray(targets, dtype=float),
        }
    )


def generate_setups(features: pd.DataFrame, config: BarrierConfig) -> pd.DataFrame:
    """Return every candidate setup on the 4h grid for one pair."""
    close = features["close"]
    parts = [
        _rows(features, close > features["donchian_high"], 1, BREAKOUT, config),
        _rows(features, close < features["donchian_low"], -1, BREAKOUT, config),
        _rows(features, features["rsi"] < 30.0, 1, REVERSION, config),
        _rows(features, features["rsi"] > 70.0, -1, REVERSION, config),
    ]
    parts = [part for part in parts if not part.empty]
    if not parts:
        return pd.DataFrame()
    setups = pd.concat(parts, ignore_index=True)
    return setups.sort_values("decision_time").reset_index(drop=True)


def random_setups(
    features: pd.DataFrame,
    config: BarrierConfig,
    count: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Random entries with identical ATR geometry, for the benchmark."""
    eligible = features[features["atr"].notna() & (features["atr"] > 0)]
    if eligible.empty or count <= 0:
        return pd.DataFrame()
    positions = rng.choice(len(eligible), size=min(count, len(eligible)), replace=False)
    selected = eligible.iloc[np.sort(positions)]
    sides = rng.choice([1, -1], size=len(selected))
    entry = selected["close"].to_numpy(dtype=float)
    atr_values = selected["atr"].to_numpy(dtype=float)
    stops, targets = zip(
        *(
            barrier_prices(e, int(s), a, config)
            for e, s, a in zip(entry, sides, atr_values, strict=True)
        ),
        strict=True,
    )
    return pd.DataFrame(
        {
            "decision_time": selected["decision_time"].to_numpy(),
            "bar_time": selected.index,
            "side": sides,
            "family": "random",
            "entry_price": entry,
            "atr": atr_values,
            "stop_price": np.asarray(stops, dtype=float),
            "target_price": np.asarray(targets, dtype=float),
        }
    )
