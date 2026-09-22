"""Purchase schedules.

Every schedule answers the same question: given `monthly` dollars arriving on
the first day of each month in `months`, on which days is that money actually
spent? A schedule returns a `pd.Series` of USD spend indexed by purchase date.

Two invariants hold for every schedule and are enforced by the tests:

1. **Same total.** Each schedule spends exactly `monthly * len(months)` over the
   campaign. The comparison is about timing, never about deploying more capital.
2. **No look-ahead.** The spend on day *t* depends only on closes up to and
   including *t*. Calendar facts that are knowable in advance (how many days a
   month has, which day of the week a date is) are not look-ahead; future
   prices are. Weighted schedules read the close of the day they trade on,
   which is what a person placing a market order at the close actually sees.

Money is not permitted to leak out of the campaign: whatever a schedule has not
spent by the last day of the window is spent on that last day. Otherwise a
schedule could "win" by quietly ending in cash, which is a different bet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Weighted schedules move the daily spend between 0.5x and 2.0x of the pace that
# would finish the month evenly. Bounded on purpose: an unbounded weight turns a
# savings plan into a leveraged view.
MIN_WEIGHT = 0.5
MAX_WEIGHT = 2.0


def month_days(prices: pd.Series, month: pd.Period) -> pd.DatetimeIndex:
    """Trading days of `month` present in `prices`, in order."""
    mask = prices.index.to_period("M") == month
    return prices.index[mask]


def _resolve_day(days: pd.DatetimeIndex, target_day: int) -> pd.Timestamp:
    """The first bar on or after `target_day`; the month's last bar if none."""
    on_or_after = days[days.day >= target_day]
    return on_or_after[0] if len(on_or_after) else days[-1]


def _as_series(spends: dict[pd.Timestamp, float]) -> pd.Series:
    if not spends:
        return pd.Series(dtype=float)
    series = pd.Series(spends).sort_index()
    series.index.name = "date"
    return series


def fixed_day(prices: pd.Series, months: list[pd.Period], monthly: float, day: int) -> pd.Series:
    """One buy per month on calendar day `day` (1..28)."""
    spends: dict[pd.Timestamp, float] = {}
    for month in months:
        days = month_days(prices, month)
        if not len(days):
            continue
        stamp = _resolve_day(days, day)
        spends[stamp] = spends.get(stamp, 0.0) + monthly
    return _as_series(spends)


def weekly_split(
    prices: pd.Series,
    months: list[pd.Period],
    monthly: float,
    anchors: tuple[int, ...] = (1, 8, 15, 22),
) -> pd.Series:
    """The monthly amount split into four equal buys inside the month."""
    spends: dict[pd.Timestamp, float] = {}
    slice_amount = monthly / len(anchors)
    for month in months:
        days = month_days(prices, month)
        if not len(days):
            continue
        for anchor in anchors:
            stamp = _resolve_day(days, anchor)
            spends[stamp] = spends.get(stamp, 0.0) + slice_amount
    return _as_series(spends)


def daily_split(prices: pd.Series, months: list[pd.Period], monthly: float) -> pd.Series:
    """The monthly amount spread evenly over every day of the month."""
    spends: dict[pd.Timestamp, float] = {}
    for month in months:
        days = month_days(prices, month)
        if not len(days):
            continue
        slice_amount = monthly / len(days)
        for stamp in days:
            spends[stamp] = spends.get(stamp, 0.0) + slice_amount
    return _as_series(spends)


def trailing_percentile(prices: pd.Series, window: int) -> pd.Series:
    """Rank of each close inside the trailing `window` closes, including itself.

    0.0 = the cheapest price in the window, 1.0 = the most expensive. Strictly
    causal: `rolling` only ever looks backwards. Days without a full window are
    NaN and are treated as weight 1.0 by the callers.
    """

    def rank(values: np.ndarray) -> float:
        last = values[-1]
        return float((values < last).sum()) / float(len(values) - 1)

    return prices.rolling(window, min_periods=window).apply(rank, raw=True)


def percentile_weights(prices: pd.Series, window: int) -> pd.Series:
    """2.0x at the bottom of the trailing distribution, 0.5x at the top."""
    percentile = trailing_percentile(prices, window)
    weights = MAX_WEIGHT - (MAX_WEIGHT - MIN_WEIGHT) * percentile
    return weights.fillna(1.0)


def ma_distance_weights(prices: pd.Series, window: int = 200, slope: float = 2.5) -> pd.Series:
    """Weight from distance below/above the trailing simple moving average."""
    average = prices.rolling(window, min_periods=window).mean()
    ratio = prices / average
    weights = 1.0 + slope * (1.0 - ratio)
    return weights.clip(MIN_WEIGHT, MAX_WEIGHT).fillna(1.0)


def weighted_split(
    prices: pd.Series, months: list[pd.Period], monthly: float, weights: pd.Series
) -> pd.Series:
    """Daily cadence whose pace is tilted by `weights`, month budget preserved.

    On each day the schedule spends `w_t` times the even pace that would finish
    the month's budget over the days remaining, capped by what is left. The last
    day of the month spends the remainder. So the month always spends exactly
    `monthly` regardless of the weights, and no future price is consulted: the
    number of days left in the month is a calendar fact.
    """
    spends: dict[pd.Timestamp, float] = {}
    for month in months:
        days = month_days(prices, month)
        if not len(days):
            continue
        remaining = monthly
        for position, stamp in enumerate(days):
            days_left = len(days) - position
            if days_left == 1:
                amount = remaining
            else:
                weight = float(weights.get(stamp, 1.0))
                weight = min(max(weight, MIN_WEIGHT), MAX_WEIGHT)
                amount = min(remaining, weight * remaining / days_left)
            amount = max(amount, 0.0)
            if amount > 0:
                spends[stamp] = spends.get(stamp, 0.0) + amount
            remaining -= amount
    return _as_series(spends)


def dip_band(
    prices: pd.Series,
    months: list[pd.Period],
    monthly: float,
    *,
    drawdown: float = 0.10,
    lookback: int = 365,
    max_wait_months: int = 3,
) -> tuple[pd.Series, dict[str, float]]:
    """Hold the monthly amount in cash until a drawdown from the trailing high.

    The trailing high is a causal rolling max over `lookback` days. Cash that has
    waited longer than `max_wait_months` is deployed at the end of that month
    regardless (without a rule like this the schedule simply sits in cash and
    stops being a savings plan). Anything still unspent on the campaign's final
    day is spent there.

    Returns the spend series plus diagnostics about how much of the time the
    plan was holding cash.
    """
    high = prices.rolling(lookback, min_periods=30).max()
    trigger = high * (1.0 - drawdown)

    spends: dict[pd.Timestamp, float] = {}
    # Each pending parcel: [amount, month index it arrived in].
    pending: list[list[float]] = []
    cash_day_dollars = 0.0
    forced = 0.0
    triggered = 0.0

    all_days: list[pd.Timestamp] = []
    for month_index, month in enumerate(months):
        days = month_days(prices, month)
        if not len(days):
            continue
        all_days.extend(days)
        pending.append([monthly, month_index])
        for position, stamp in enumerate(days):
            held = sum(parcel[0] for parcel in pending)
            cash_day_dollars += held

            close = prices.loc[stamp]
            level = trigger.loc[stamp]
            is_dip = bool(pd.notna(level) and close <= level)
            if is_dip and held > 0:
                spends[stamp] = spends.get(stamp, 0.0) + held
                triggered += held
                pending = []
                continue

            if position == len(days) - 1:
                expired = [p for p in pending if month_index - p[1] >= max_wait_months]
                amount = sum(p[0] for p in expired)
                if amount > 0:
                    spends[stamp] = spends.get(stamp, 0.0) + amount
                    forced += amount
                    pending = [p for p in pending if month_index - p[1] < max_wait_months]

    leftover = sum(parcel[0] for parcel in pending)
    if leftover > 0 and all_days:
        last = all_days[-1]
        spends[last] = spends.get(last, 0.0) + leftover
        forced += leftover

    total = monthly * len(months)
    diagnostics = {
        "share_deployed_on_dip": triggered / total if total else float("nan"),
        "share_deployed_by_timeout": forced / total if total else float("nan"),
        "mean_cash_held_months": (cash_day_dollars / len(all_days) / monthly) if all_days else 0.0,
    }
    return _as_series(spends), diagnostics
