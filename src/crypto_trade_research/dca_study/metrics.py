"""Campaign metrics and confidence intervals.

The headline number is the **average cost basis**: dollars spent divided by
units bought. Everything else is a way of putting that number on a scale.

Two reference points matter and they are not the same:

* `mean_price` - the arithmetic mean of the daily closes in the window. This is
  the "what a month is worth" benchmark. Note that *any* schedule which splits
  a fixed dollar amount evenly across days achieves the **harmonic** mean of
  those prices, which is always <= the arithmetic mean. So beating the
  arithmetic mean is not evidence of skill; it is an artefact of buying a fixed
  dollar amount rather than a fixed number of coins.
* `best` / `worst` - the minimum and maximum close in the window, i.e. the cost
  basis of a clairvoyant who spent everything at the single best or worst
  moment. The gap between them sets the scale of what timing could ever be
  worth, and it is enormous compared with the differences between schedules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CampaignResult:
    symbol: str
    schedule: str
    start: pd.Timestamp
    end: pd.Timestamp
    months: int
    spent: float
    units: float
    cost_basis: float
    mean_price: float
    harmonic_mean_price: float
    best_price: float
    worst_price: float
    terminal_value: float
    basis_vs_mean_pct: float
    basis_vs_harmonic_pct: float
    position_in_range: float

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate(
    symbol: str,
    schedule: str,
    prices: pd.Series,
    spends: pd.Series,
    window: pd.DatetimeIndex,
) -> CampaignResult:
    """Score one schedule over one campaign window."""
    if spends.empty:
        raise ValueError("schedule produced no purchases")

    paid = prices.reindex(spends.index)
    if paid.isna().any():
        raise ValueError("schedule bought on a day with no price")

    spent = float(spends.sum())
    units = float((spends / paid).sum())
    cost_basis = spent / units

    window_prices = prices.reindex(window).dropna()
    mean_price = float(window_prices.mean())
    harmonic = float(len(window_prices) / (1.0 / window_prices).sum())
    best = float(window_prices.min())
    worst = float(window_prices.max())
    terminal = units * float(window_prices.iloc[-1])

    return CampaignResult(
        symbol=symbol,
        schedule=schedule,
        start=window_prices.index[0],
        end=window_prices.index[-1],
        months=len(pd.PeriodIndex(window_prices.index, freq="M").unique()),
        spent=spent,
        units=units,
        cost_basis=cost_basis,
        mean_price=mean_price,
        harmonic_mean_price=harmonic,
        best_price=best,
        worst_price=worst,
        terminal_value=terminal,
        basis_vs_mean_pct=100.0 * (cost_basis / mean_price - 1.0),
        basis_vs_harmonic_pct=100.0 * (cost_basis / harmonic - 1.0),
        position_in_range=(cost_basis - best) / (worst - best) if worst > best else float("nan"),
    )


def moving_block_bootstrap_ci(
    values: np.ndarray,
    *,
    block: int = 12,
    draws: int = 5000,
    alpha: float = 0.05,
    seed: int = 20260922,
) -> tuple[float, float, float]:
    """Mean and a moving-block bootstrap CI for an overlapping-campaign series.

    Campaigns started in consecutive months share almost all of their data, so
    the observations are heavily autocorrelated and an iid bootstrap would give
    an interval several times too tight. Blocks of `block` consecutive start
    months keep that dependence in the resamples.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    n = values.size
    if n == 0:
        return (float("nan"),) * 3
    if n <= block:
        return float(values.mean()), float(values.min()), float(values.max())

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(draws, n_blocks))
    offsets = np.arange(block)
    index = (starts[:, :, None] + offsets[None, None, :]).reshape(draws, -1)[:, :n]
    means = values[index].mean(axis=1)
    low, high = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(values.mean()), float(low), float(high)
