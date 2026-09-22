"""Is a per-trade expectancy distinguishable from zero, or from another set?

Trades from overlapping 4h setups are not independent: neighbouring setups on
the same pair share price path, and setups across pairs at the same moment share
the market. A plain t-test on 2,400 such trades overstates confidence badly, so
the interval here comes from a MOVING-BLOCK bootstrap, which resamples
contiguous blocks and therefore keeps local dependence intact.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Interval:
    mean: float
    lower: float
    upper: float
    t_statistic: float
    samples: int
    block: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "mean": self.mean,
            "ci_lower": self.lower,
            "ci_upper": self.upper,
            "naive_t_statistic": self.t_statistic,
            "samples": self.samples,
            "block_size": self.block,
        }


def block_bootstrap_mean(
    values: np.ndarray,
    block: int = 30,
    iterations: int = 5000,
    confidence: float = 0.95,
    seed: int = 11,
) -> Interval:
    values = np.asarray(values, dtype=float)
    count = values.size
    if count < 2:
        return Interval(float("nan"), float("nan"), float("nan"), float("nan"), count, block)

    block = max(1, min(block, count))
    rng = np.random.default_rng(seed)
    blocks_needed = int(np.ceil(count / block))
    starts = rng.integers(0, count - block + 1, size=(iterations, blocks_needed))
    offsets = np.arange(block)
    means = np.empty(iterations)
    for iteration in range(iterations):
        indices = (starts[iteration][:, None] + offsets).ravel()[:count]
        means[iteration] = values[indices].mean()

    tail = (1.0 - confidence) / 2.0
    deviation = values.std(ddof=1)
    t_statistic = float(values.mean() / (deviation / np.sqrt(count))) if deviation > 0 else 0.0
    return Interval(
        mean=float(values.mean()),
        lower=float(np.quantile(means, tail)),
        upper=float(np.quantile(means, 1.0 - tail)),
        t_statistic=t_statistic,
        samples=count,
        block=block,
    )


def difference_interval(
    left: np.ndarray,
    right: np.ndarray,
    block: int = 30,
    iterations: int = 5000,
    confidence: float = 0.95,
    seed: int = 11,
) -> Interval:
    """Bootstrap the difference of two independent trade sets' mean R."""
    left_interval = block_bootstrap_mean(left, block, iterations, confidence, seed)
    right_interval = block_bootstrap_mean(right, block, iterations, confidence, seed + 1)
    spread = left_interval.mean - right_interval.mean
    # Independent sets, so the interval half-widths add in quadrature.
    left_half = (left_interval.upper - left_interval.lower) / 2.0
    right_half = (right_interval.upper - right_interval.lower) / 2.0
    half = float(np.hypot(left_half, right_half))
    return Interval(
        mean=spread,
        lower=spread - half,
        upper=spread + half,
        t_statistic=float("nan"),
        samples=left_interval.samples + right_interval.samples,
        block=block,
    )
