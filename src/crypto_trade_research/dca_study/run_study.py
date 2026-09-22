"""CLI: `crypto-trade-run-dca-study`."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .data import DEFAULT_CACHE, MAJORS, UNIVERSE, load_universe
from .metrics import moving_block_bootstrap_ci
from .study import (
    MEAN_FIXED_DAY,
    MONTHLY,
    day_of_month_stability,
    day_of_month_table,
    monthly_intramonth_bias,
    run_symbol,
    summarise,
)

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spot DCA execution-timing study")
    parser.add_argument("--pairs", default=",".join(UNIVERSE))
    parser.add_argument("--length-months", type=int, default=36)
    parser.add_argument(
        "--baseline",
        default=MEAN_FIXED_DAY,
        help="'mean_fixed_day' (default) or a schedule name such as fixed_day_01",
    )
    parser.add_argument("--monthly", type=float, default=MONTHLY)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--out-dir", default="reports/dca-study")
    parser.add_argument("--offline", action="store_true", help="use cache only")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    symbols = [s.strip().upper() for s in args.pairs.split(",") if s.strip()]
    universe = load_universe(symbols, cache_dir=args.cache_dir, allow_download=not args.offline)
    if not universe:
        LOGGER.error("no series loaded")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    coverage = pd.DataFrame(
        [
            {
                "symbol": s.symbol,
                "start": str(s.start.date()),
                "end": str(s.end.date()),
                "days": len(s.frame),
            }
            for s in universe.values()
        ]
    )
    print("\n== coverage ==")
    print(coverage.to_string(index=False))

    all_campaigns: list[pd.DataFrame] = []
    all_diagnostics: list[pd.DataFrame] = []
    for symbol, series in universe.items():
        campaigns, diagnostics = run_symbol(
            series, length_months=args.length_months, monthly=args.monthly
        )
        if campaigns.empty:
            LOGGER.warning(
                "%s: too little history for %d-month campaigns", symbol, args.length_months
            )
            continue
        all_campaigns.append(campaigns)
        if not diagnostics.empty:
            all_diagnostics.append(diagnostics)

    campaigns = pd.concat(all_campaigns, ignore_index=True)
    campaigns.to_parquet(out_dir / "campaigns.parquet")

    baseline = args.baseline

    print(f"\n== schedules vs {baseline}, majors only (BTC, ETH) ==")
    majors = campaigns[campaigns["symbol"].isin(MAJORS)]
    majors_summary = summarise(majors, baseline)
    print(majors_summary.to_string(index=False, float_format=lambda v: f"{v: .3f}"))
    majors_summary.to_csv(out_dir / "summary_majors.csv", index=False)

    print("\n== schedules vs baseline, full universe ==")
    full_summary = summarise(campaigns, baseline)
    print(full_summary.to_string(index=False, float_format=lambda v: f"{v: .3f}"))
    full_summary.to_csv(out_dir / "summary_universe.csv", index=False)

    print("\n== per-symbol, splitting and weighting only ==")
    keep = ["daily_split", "weekly_split", "pct_weighted_90", "pct_weighted_180", "ma200_weighted"]
    per_symbol = []
    for symbol in campaigns["symbol"].unique():
        part = campaigns[campaigns["symbol"] == symbol]
        summary = summarise(part, baseline)
        for _, row in summary[summary["schedule"].isin(keep)].iterrows():
            per_symbol.append(
                {
                    "symbol": symbol,
                    "schedule": row["schedule"],
                    "vs_baseline_pct": row["basis_vs_baseline_pct"],
                    "ci_low": row["ci_low"],
                    "ci_high": row["ci_high"],
                }
            )
    per_symbol_frame = pd.DataFrame(per_symbol)
    print(per_symbol_frame.to_string(index=False, float_format=lambda v: f"{v: .3f}"))
    per_symbol_frame.to_csv(out_dir / "per_symbol.csv", index=False)

    print("\n== day of month, majors (vs the mean of all 28 fixed days) ==")
    days = day_of_month_table(majors)
    print(days.to_string(index=False, float_format=lambda v: f"{v: .3f}"))
    days.to_csv(out_dir / "day_of_month_majors.csv", index=False)

    print("\n== day-of-month stability: first half of history vs second ==")
    for label, part in (("majors", majors), ("universe", campaigns)):
        print(f"{label}: {day_of_month_stability(part)}")

    print("\n== intra-month bias: fixed day close vs that month's mean close ==")
    # This is the cleanest test available: one observation per calendar month,
    # so the samples do not overlap the way rolling campaigns do.
    bias_rows = []
    for symbol, series in universe.items():
        for day in range(1, 29):
            bias = monthly_intramonth_bias(series.close, day)
            mean, low, high = moving_block_bootstrap_ci(bias.to_numpy(), block=6)
            bias_rows.append(
                {
                    "symbol": symbol,
                    "day": day,
                    "months": int(bias.notna().sum()),
                    "mean_pct": mean,
                    "ci_low": low,
                    "ci_high": high,
                    "sd_pct": float(np.nanstd(bias.to_numpy())),
                    "share_above_mean": float((bias > 0).mean()),
                }
            )
    bias_frame = pd.DataFrame(bias_rows)
    bias_frame.to_csv(out_dir / "intramonth_bias.csv", index=False)

    print(
        bias_frame[bias_frame["day"].isin([1, 5, 10, 12, 15, 20, 25, 28])].to_string(
            index=False, float_format=lambda v: f"{v: .3f}"
        )
    )

    print("\n== intra-month bias, pooled over days, per symbol ==")
    pooled = bias_frame.groupby("symbol").agg(
        mean_of_day_means=("mean_pct", "mean"),
        worst_day=("mean_pct", "max"),
        best_day=("mean_pct", "min"),
        typical_month_sd=("sd_pct", "mean"),
        days_with_ci_excluding_zero=(
            "mean_pct",
            lambda _: int(
                (
                    (bias_frame.loc[_.index, "ci_low"] > 0)
                    | (bias_frame.loc[_.index, "ci_high"] < 0)
                ).sum()
            ),
        ),
    )
    print(pooled.to_string(float_format=lambda v: f"{v: .3f}"))
    pooled.to_csv(out_dir / "intramonth_bias_pooled.csv")

    if all_diagnostics:
        diagnostics = pd.concat(all_diagnostics, ignore_index=True)
        print("\n== dip-band cash behaviour ==")
        summary = diagnostics.groupby("schedule")[
            ["share_deployed_on_dip", "share_deployed_by_timeout", "mean_cash_held_months"]
        ].mean()
        print(summary.to_string(float_format=lambda v: f"{v: .3f}"))
        diagnostics.to_csv(out_dir / "dip_diagnostics.csv", index=False)

    (out_dir / "meta.json").write_text(
        json.dumps(
            {
                "pairs": list(universe),
                "length_months": args.length_months,
                "baseline": baseline,
                "campaigns": int(len(campaigns)),
                "coverage": coverage.to_dict("records"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
