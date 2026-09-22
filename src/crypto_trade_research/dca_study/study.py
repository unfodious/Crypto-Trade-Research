"""Run every schedule over every rolling start month and tabulate the result."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import schedules as sched
from .data import Series
from .metrics import evaluate, moving_block_bootstrap_ci

MONTHLY = 1000.0  # the unit of spend; every metric is scale-free in it


@dataclass(frozen=True)
class ScheduleSpec:
    name: str
    kind: str
    params: dict


def default_specs(fixed_days: tuple[int, ...] = tuple(range(1, 29))) -> list[ScheduleSpec]:
    specs = [ScheduleSpec(f"fixed_day_{d:02d}", "fixed_day", {"day": d}) for d in fixed_days]
    specs += [
        ScheduleSpec("weekly_split", "weekly", {}),
        ScheduleSpec("daily_split", "daily", {}),
        ScheduleSpec("pct_weighted_90", "percentile", {"window": 90}),
        ScheduleSpec("pct_weighted_180", "percentile", {"window": 180}),
        ScheduleSpec("ma200_weighted", "ma", {"window": 200}),
        ScheduleSpec("dip_band_10pct", "dip", {"drawdown": 0.10}),
        ScheduleSpec("dip_band_20pct", "dip", {"drawdown": 0.20}),
    ]
    return specs


def weight_cache(prices: pd.Series, specs: list[ScheduleSpec]) -> dict[str, pd.Series]:
    """Weight series depend only on the price history, not on the campaign.

    Computing them once per symbol instead of once per (campaign, schedule) is
    the difference between seconds and minutes, and it also guarantees that two
    campaigns see identical weights on a shared date.
    """
    cache: dict[str, pd.Series] = {}
    for spec in specs:
        if spec.kind == "percentile":
            cache[spec.name] = sched.percentile_weights(prices, spec.params["window"])
        elif spec.kind == "ma":
            cache[spec.name] = sched.ma_distance_weights(prices, spec.params["window"])
    return cache


def _spends_for(
    spec: ScheduleSpec,
    prices: pd.Series,
    months: list[pd.Period],
    monthly: float,
    weights: dict[str, pd.Series] | None = None,
) -> tuple[pd.Series, dict]:
    weights = weights or {}
    if spec.kind == "fixed_day":
        return sched.fixed_day(prices, months, monthly, spec.params["day"]), {}
    if spec.kind == "weekly":
        return sched.weekly_split(prices, months, monthly), {}
    if spec.kind == "daily":
        return sched.daily_split(prices, months, monthly), {}
    if spec.kind in ("percentile", "ma"):
        series = weights.get(spec.name)
        if series is None:
            series = weight_cache(prices, [spec])[spec.name]
        return sched.weighted_split(prices, months, monthly, series), {}
    if spec.kind == "dip":
        return sched.dip_band(prices, months, monthly, drawdown=spec.params["drawdown"])
    raise ValueError(f"unknown schedule kind {spec.kind}")


def campaign_months(prices: pd.Series) -> list[pd.Period]:
    """Complete months in the series (a partial first/last month is dropped)."""
    periods = pd.PeriodIndex(prices.index, freq="M")
    unique = list(dict.fromkeys(periods))
    keep = []
    for period in unique:
        days = prices.index[periods == period]
        if days[0].day <= 3 and days[-1].day >= 27:
            keep.append(period)
    return keep


def run_symbol(
    series: Series,
    *,
    length_months: int = 36,
    monthly: float = MONTHLY,
    specs: list[ScheduleSpec] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run every schedule over every rolling `length_months` campaign.

    Returns (per-campaign rows, dip diagnostics rows).
    """
    prices = series.close
    specs = specs or default_specs()
    months = campaign_months(prices)
    weights = weight_cache(prices, specs)

    rows: list[dict] = []
    diagnostics: list[dict] = []
    for offset in range(0, len(months) - length_months + 1):
        window_months = months[offset : offset + length_months]
        mask = pd.PeriodIndex(prices.index, freq="M").isin(window_months)
        window = prices.index[mask]
        for spec in specs:
            spends, extra = _spends_for(spec, prices, window_months, monthly, weights)
            result = evaluate(series.symbol, spec.name, prices, spends, window)
            rows.append(result.as_dict() | {"start_month": str(window_months[0])})
            if extra:
                diagnostics.append(
                    {
                        "symbol": series.symbol,
                        "schedule": spec.name,
                        "start_month": str(window_months[0]),
                    }
                    | extra
                )
    return pd.DataFrame(rows), pd.DataFrame(diagnostics)


MEAN_FIXED_DAY = "mean_fixed_day"


def _reference(pivot: pd.DataFrame, baseline: str) -> pd.Series:
    """The series each schedule is compared against.

    `mean_fixed_day` is the honest default. Picking any single calendar day as
    the baseline biases every comparison by however lucky that day happened to
    be in this sample, and some days are lucky by a full percent. The average
    cost basis of all 28 fixed days is what "an arbitrary fixed monthly buy"
    actually costs, and that is the thing the user is doing.
    """
    if baseline == MEAN_FIXED_DAY:
        fixed = [c for c in pivot.columns if c.startswith("fixed_day_")]
        return pivot[fixed].mean(axis=1)
    return pivot[baseline]


def summarise(campaigns: pd.DataFrame, baseline: str) -> pd.DataFrame:
    """Per-schedule mean cost basis, and the paired difference vs `baseline`.

    The paired difference is what the question is actually about: for the same
    start month and the same asset, how much cheaper (in percent of cost basis)
    is this schedule than the baseline? Pairing removes the enormous variance
    that comes from *when* you started, which otherwise swamps everything.
    """
    pivot = campaigns.pivot_table(
        index=["symbol", "start_month"], columns="schedule", values="cost_basis"
    )
    reference = _reference(pivot, baseline)

    out = []
    for schedule in pivot.columns:
        difference = 100.0 * (pivot[schedule] / reference - 1.0)
        mean, low, high = moving_block_bootstrap_ci(difference.to_numpy())
        absolute = campaigns.loc[campaigns["schedule"] == schedule, "basis_vs_mean_pct"]
        abs_mean, abs_low, abs_high = moving_block_bootstrap_ci(absolute.to_numpy())
        out.append(
            {
                "schedule": schedule,
                "campaigns": int(difference.notna().sum()),
                "basis_vs_baseline_pct": mean,
                "ci_low": low,
                "ci_high": high,
                "basis_vs_window_mean_pct": abs_mean,
                "window_mean_ci_low": abs_low,
                "window_mean_ci_high": abs_high,
                "spread_p5_p95_pct": float(
                    np.nanpercentile(difference, 95) - np.nanpercentile(difference, 5)
                ),
            }
        )
    return pd.DataFrame(out).sort_values("basis_vs_baseline_pct").reset_index(drop=True)


def day_of_month_table(campaigns: pd.DataFrame) -> pd.DataFrame:
    """Only the 28 fixed-day schedules, ranked, with CIs on the paired gap.

    The comparison is against the mean of all 28 fixed days for the same
    campaign, so the question is "is *this* day unlucky relative to the other
    days", not "is a fixed day unlucky relative to the mean price".
    """
    fixed = campaigns[campaigns["schedule"].str.startswith("fixed_day_")]
    pivot = fixed.pivot_table(
        index=["symbol", "start_month"], columns="schedule", values="cost_basis"
    )
    reference = pivot.mean(axis=1)

    rows = []
    for schedule in pivot.columns:
        difference = 100.0 * (pivot[schedule] / reference - 1.0)
        mean, low, high = moving_block_bootstrap_ci(difference.to_numpy())
        rows.append(
            {
                "day": int(schedule.split("_")[-1]),
                "basis_vs_all_days_pct": mean,
                "ci_low": low,
                "ci_high": high,
            }
        )
    return pd.DataFrame(rows).sort_values("day").reset_index(drop=True)


def day_of_month_stability(campaigns: pd.DataFrame) -> dict[str, float]:
    """Does the day-of-month ranking found in the first half survive the second?

    With 28 days tested on two correlated assets, some day will always look
    significantly cheap in-sample. The only question that matters is whether
    the ranking repeats out of sample. A Spearman correlation near zero means
    the winning day is a data-mining artefact and must not be recommended.
    """
    fixed = campaigns[campaigns["schedule"].str.startswith("fixed_day_")]
    starts = sorted(fixed["start_month"].unique())
    if len(starts) < 8:
        return {"spearman": float("nan"), "first_half_best_day": float("nan")}
    split = starts[len(starts) // 2]

    def ranking(part: pd.DataFrame) -> pd.Series:
        pivot = part.pivot_table(
            index=["symbol", "start_month"], columns="schedule", values="cost_basis"
        )
        relative = pivot.div(pivot.mean(axis=1), axis=0)
        return relative.mean(axis=0)

    first = ranking(fixed[fixed["start_month"] < split])
    second = ranking(fixed[fixed["start_month"] >= split])
    common = first.index.intersection(second.index)
    first, second = first[common], second[common]

    spearman = float(
        np.corrcoef(pd.Series(first).rank().to_numpy(), pd.Series(second).rank().to_numpy())[0, 1]
    )
    best_first = str(first.idxmin())
    return {
        "spearman": spearman,
        "first_half_best_day": float(best_first.split("_")[-1]),
        "second_half_best_day": float(str(second.idxmin()).split("_")[-1]),
        "first_half_best_day_rank_in_second_half": float(second.rank().loc[best_first]),
        "days": int(len(common)),
    }


def monthly_intramonth_bias(prices: pd.Series, day: int) -> pd.Series:
    """Per-month: the close on day `day` relative to that month's mean close.

    This is the most direct test of "I always buy at local highs". A positive
    number means the fixed day paid above the month's average price.
    """
    periods = pd.PeriodIndex(prices.index, freq="M")
    out = {}
    for period in dict.fromkeys(periods):
        days = prices.index[periods == period]
        if len(days) < 25:
            continue
        on_or_after = days[days.day >= day]
        stamp = on_or_after[0] if len(on_or_after) else days[-1]
        month_prices = prices.loc[days]
        out[str(period)] = 100.0 * (prices.loc[stamp] / month_prices.mean() - 1.0)
    return pd.Series(out, dtype=float)
