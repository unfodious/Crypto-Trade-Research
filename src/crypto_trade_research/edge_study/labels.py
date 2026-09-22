"""Triple-barrier labelling resolved on the 1m path.

For each candidate setup we know the entry (the 4h bar's close), an ATR-scaled
stop and target, and a horizon. The label is which barrier was touched FIRST.
The ordering question is why the 1m series is kept: a 4h bar whose high exceeds
the target and whose low breaches the stop is ambiguous from OHLC alone. Here we
walk the 1m bars and take the first touch, and when a single 1m bar touches both
we resolve it as the STOP (pessimistic, so the label can never flatter a setup).

Outputs per setup: the barrier hit, exit price, exit time, realized R before
costs, and MFE/MAE in R.

Leakage: the scan starts at the first 1m bar at or after `decision_time` - the
entry bar's own path is never used to build a feature, and a feature is never
used that was not closed by `decision_time`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TARGET = "target"
STOP = "stop"
TIMEOUT = "timeout"


@dataclass(frozen=True)
class BarrierConfig:
    stop_atr: float = 1.5
    target_atr: float = 3.0
    horizon_bars: int = 30
    bar_hours: float = 4.0


def _resolve_one(
    highs: np.ndarray,
    lows: np.ndarray,
    side: int,
    entry: float,
    stop: float,
    target: float,
) -> tuple[str, int, float, float]:
    """Return (barrier, index into the slice, mfe_price, mae_price)."""
    if side > 0:
        stop_hits = lows <= stop
        target_hits = highs >= target
        favourable, adverse = highs, lows
    else:
        stop_hits = highs >= stop
        target_hits = lows <= target
        favourable, adverse = lows, highs

    stop_index = int(np.argmax(stop_hits)) if stop_hits.any() else len(highs)
    target_index = int(np.argmax(target_hits)) if target_hits.any() else len(highs)

    if stop_index == len(highs) and target_index == len(highs):
        end = len(highs) - 1
        return TIMEOUT, end, _extreme(favourable, side, end), _extreme(adverse, -side, end)
    # Ties inside one minute resolve as the stop: never flatter the setup.
    if stop_index <= target_index:
        return STOP, stop_index, _extreme(favourable, side, stop_index), stop
    return TARGET, target_index, target, _extreme(adverse, -side, target_index)


def _extreme(values: np.ndarray, direction: int, end_index: int) -> float:
    window = values[: end_index + 1]
    if window.size == 0:
        return float("nan")
    return float(window.max() if direction > 0 else window.min())


def label_setups(
    setups: pd.DataFrame,
    minute: pd.DataFrame,
    config: BarrierConfig,
) -> pd.DataFrame:
    """Attach barrier outcomes to `setups`.

    `setups` needs columns: decision_time, side, entry_price, stop_price,
    target_price. `minute` is the 1m frame indexed by open time (UTC).
    """
    required = {"decision_time", "side", "entry_price", "stop_price", "target_price"}
    missing = required - set(setups.columns)
    if missing:
        raise ValueError(f"setups missing columns: {sorted(missing)}")

    minute_times = minute.index
    highs_all = minute["high"].to_numpy(dtype=float)
    lows_all = minute["low"].to_numpy(dtype=float)
    closes_all = minute["close"].to_numpy(dtype=float)

    horizon = pd.Timedelta(hours=config.bar_hours * config.horizon_bars)
    rows = []
    for setup in setups.itertuples(index=False):
        start = int(minute_times.searchsorted(setup.decision_time, side="left"))
        stop_at = int(minute_times.searchsorted(setup.decision_time + horizon, side="right"))
        if stop_at - start < 2:
            continue
        highs = highs_all[start:stop_at]
        lows = lows_all[start:stop_at]
        side = int(setup.side)
        barrier, index, mfe_price, mae_price = _resolve_one(
            highs, lows, side, setup.entry_price, setup.stop_price, setup.target_price
        )
        if barrier == TARGET:
            exit_price = float(setup.target_price)
        elif barrier == STOP:
            exit_price = float(setup.stop_price)
        else:
            exit_price = float(closes_all[start + index])
        risk = abs(setup.entry_price - setup.stop_price)
        exit_time = minute_times[start + index]
        rows.append(
            {
                "barrier": barrier,
                "exit_time": exit_time,
                "exit_price": exit_price,
                "risk_per_unit": risk,
                "gross_r": side * (exit_price - setup.entry_price) / risk,
                "mfe_r": side * (mfe_price - setup.entry_price) / risk,
                "mae_r": side * (mae_price - setup.entry_price) / risk,
                "bars_held": (exit_time - setup.decision_time).total_seconds()
                / 3600.0
                / config.bar_hours,
                "_setup_key": (setup.decision_time, side),
            }
        )

    if not rows:
        return setups.iloc[0:0].copy()

    labelled = pd.DataFrame(rows)
    keys = list(zip(setups["decision_time"], setups["side"].astype(int), strict=True))
    setups = setups.assign(_setup_key=keys)
    merged = setups.merge(labelled, on="_setup_key", how="inner").drop(columns="_setup_key")
    merged["hours_held"] = merged["bars_held"] * config.bar_hours
    merged["win"] = (merged["barrier"] == TARGET).astype(int)
    return merged


def barrier_prices(
    entry_price: float, side: int, atr_value: float, config: BarrierConfig
) -> tuple[float, float]:
    """Stop and target prices for one side, scaled by ATR."""
    stop_distance = config.stop_atr * atr_value
    target_distance = config.target_atr * atr_value
    if side > 0:
        return entry_price - stop_distance, entry_price + target_distance
    return entry_price + stop_distance, entry_price - target_distance
