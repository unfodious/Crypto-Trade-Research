"""Runner for the cross-sectional relative-strength study.

Research only: reads local candle archives plus the cached non-price panels and
writes JSON. No exchange client, no credentials, no order path.

    uv run crypto-trade-run-cross-section
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_trade_research.edge_study import backtest as bt
from crypto_trade_research.edge_study import cross_section as cs
from crypto_trade_research.edge_study import data as market
from crypto_trade_research.edge_study import features as feat
from crypto_trade_research.edge_study import labels as lab
from crypto_trade_research.edge_study import significance as sig
from crypto_trade_research.edge_study.costs import CostModel
from crypto_trade_research.edge_study.run_study import DEFAULT_END, DEFAULT_START, DEFAULT_UNIVERSE
from crypto_trade_research.edge_study.walkforward import WalkForwardConfig, run_walk_forward

LOGGER = logging.getLogger(__name__)


def _evaluate(trades: pd.DataFrame, label: str) -> dict[str, object]:
    real, _, _ = bt.simulate(trades, CostModel())
    zero, _, _ = bt.simulate(trades, CostModel.zero())
    return {"label": label, "after_costs": real.to_dict(), "before_costs": zero.to_dict()}


def _mean_metrics(rows: list[dict[str, float]]) -> dict[str, float]:
    keys = rows[0].keys()
    return {
        key: float(np.mean([row[key] for row in rows if np.isfinite(row[key])])) for key in keys
    }


def _breakdown(trades: pd.DataFrame, by: str) -> list[dict[str, object]]:
    """Per-slice expectancy after and before costs, in R per trade."""
    if trades.empty:
        return []
    _, priced, _ = bt.simulate(trades, CostModel())
    _, unpriced, _ = bt.simulate(trades, CostModel.zero())
    if priced.empty:
        return []
    keys = priced[by] if by != "period" else priced["decision_time"].dt.to_period("Q").astype(str)
    zero_keys = (
        unpriced[by] if by != "period" else unpriced["decision_time"].dt.to_period("Q").astype(str)
    )
    gross = unpriced.groupby(zero_keys)["net_r"].mean()
    rows = []
    for key, group in priced.groupby(keys):
        values = group["net_r"]
        rows.append(
            {
                by: str(key),
                "trades": int(len(group)),
                "win_rate": float((values > 0).mean()),
                "expectancy_r_after_costs": float(values.mean()),
                "expectancy_r_before_costs": float(gross.get(key, float("nan"))),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-sectional relative-strength study (research only)."
    )
    parser.add_argument("--archive", type=Path, default=market.DEFAULT_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/edge-study"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/generated/edge-study-cache"))
    parser.add_argument("--alt-cache-dir", type=Path, default=Path("data/generated/altdata-cache"))
    parser.add_argument("--no-alt-data", action="store_true")
    parser.add_argument("--feature-set", default="all", choices=sorted(feat.FEATURE_SETS))
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--pairs", default=",".join(DEFAULT_UNIVERSE))
    parser.add_argument("--stop-atr", type=float, default=1.5)
    parser.add_argument("--target-atr", type=float, default=3.0)
    parser.add_argument("--horizon-bars", type=int, default=30)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--stride-bars", type=int, default=1)
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--embargo-days", type=float, default=7.0)
    parser.add_argument("--random-seeds", type=int, default=5)
    parser.add_argument("--report-name", default="cross_section_report.json")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    universe = tuple(pair.strip() for pair in arguments.pairs.split(",") if pair.strip())
    barrier = lab.BarrierConfig(
        stop_atr=arguments.stop_atr,
        target_atr=arguments.target_atr,
        horizon_bars=arguments.horizon_bars,
    )
    book_config = cs.CrossSectionConfig(top_k=arguments.top_k, stride_bars=arguments.stride_bars)
    output_dir = arguments.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    alt_cache_dir = None if arguments.no_alt_data else arguments.alt_cache_dir

    panel, bars_by_pair = cs.build_panel(
        universe,
        arguments.archive,
        arguments.start,
        arguments.end,
        barrier,
        arguments.cache_dir,
        alt_cache_dir,
        stride=arguments.stride_bars,
    )
    longs = panel[panel["side"] == 1].reset_index(drop=True)
    shorts = panel[panel["side"] == -1].reset_index(drop=True)

    requested = feat.feature_columns(arguments.feature_set)
    available = [
        column for column in requested if column in longs.columns and longs[column].notna().any()
    ]
    usable = longs.dropna(subset=available).reset_index(drop=True)
    labelled = cs.relative_labels(usable, book_config.min_pairs_per_bar)
    ranked = cs.cross_sectional_ranks(labelled, available)
    rank_columns = [f"{cs.CROSS_PREFIX}{column}" for column in available]
    LOGGER.info(
        "panel=%d longs=%d usable=%d labelled=%d features=%d",
        len(panel),
        len(longs),
        len(usable),
        len(labelled),
        len(rank_columns),
    )

    walk_config = WalkForwardConfig(
        folds=arguments.folds, embargo_days=arguments.embargo_days, selectivity=0.5
    )
    predictions, folds = run_walk_forward(ranked, rank_columns, walk_config)
    if predictions.empty:
        raise SystemExit("cross-section walk-forward produced no out-of-sample rows")

    book = cs.build_book(predictions, shorts, book_config)
    random_book_runs = cs.random_books(predictions, shorts, book_config, arguments.random_seeds)
    hold = bt.buy_and_hold(bars_by_pair)

    evaluations = [
        _evaluate(book, f"cross_section_long_short_top{book_config.top_k}"),
        _evaluate(book[book["side"] == 1], "cross_section_long_leg_only"),
        _evaluate(book[book["side"] == -1], "cross_section_short_leg_only"),
    ]
    random_results = [_evaluate(run, "random_ranking") for run in random_book_runs]
    if random_results:
        evaluations.append(
            {
                "label": "random_ranking_mean",
                "after_costs": _mean_metrics([row["after_costs"] for row in random_results]),
                "before_costs": _mean_metrics([row["before_costs"] for row in random_results]),
                "seeds": len(random_results),
            }
        )
    evaluations.append(
        {"label": "buy_and_hold", "after_costs": hold.to_dict(), "before_costs": hold.to_dict()}
    )

    costs = CostModel()
    book_r = cs.net_r(book, costs)
    random_r = (
        np.concatenate([cs.net_r(run, costs) for run in random_book_runs])
        if random_book_runs
        else np.array([])
    )
    significance: dict[str, object] = {
        "per_trade_r_after_costs": {
            "cross_section": sig.block_bootstrap_mean(book_r).to_dict(),
        }
    }
    if random_r.size:
        significance["per_trade_r_after_costs"]["random_ranking"] = sig.block_bootstrap_mean(
            random_r
        ).to_dict()
        significance["cross_section_minus_random"] = sig.difference_interval(
            book_r, random_r
        ).to_dict()

    report = {
        "study": "cross_sectional_relative_strength",
        "window": {"start": arguments.start, "end": arguments.end},
        "universe": list(universe),
        "barrier": asdict(barrier),
        "book": asdict(book_config),
        "costs": asdict(costs),
        "feature_set": arguments.feature_set,
        "alt_data": not arguments.no_alt_data,
        "feature_columns": rank_columns,
        "sample_sizes": {
            "panel_rows": int(len(panel)),
            "long_rows": int(len(longs)),
            "usable_long_rows": int(len(usable)),
            "labelled_long_rows": int(len(labelled)),
            "oos_scored_rows": int(len(predictions)),
            "book_legs": int(len(book)),
            "relative_base_rate": float(labelled["win"].mean()) if len(labelled) else float("nan"),
        },
        "evaluations": evaluations,
        "random_ranking_runs": random_results,
        "significance": significance,
        "folds": [
            {
                "fold": fold.index,
                "test_start": str(fold.test_start),
                "test_end": str(fold.test_end),
                "train_size": fold.train_size,
                "test_size": fold.test_size,
                "train_auc": fold.train_auc,
                "auc": fold.auc,
                "metrics_after_costs": bt.simulate(book[book["fold"] == fold.index], CostModel())[
                    0
                ].to_dict(),
            }
            for fold in folds
        ],
        "breakdowns": {
            "by_pair": _breakdown(book, "pair"),
            "by_quarter": _breakdown(book, "period"),
            "by_side": _breakdown(
                book.assign(side_label=book["side"].map({1: "long", -1: "short"})), "side_label"
            ),
        },
    }

    report_path = output_dir / arguments.report_name
    report_path.write_text(json.dumps(report, indent=2, default=str))
    LOGGER.info("wrote %s", report_path)
    print(json.dumps(report["sample_sizes"], indent=2, default=str))
    for evaluation in evaluations:
        after = evaluation["after_costs"]
        print(
            f"{evaluation['label']:<38} trades={after['trades']:>5} "
            f"win={after['win_rate']:.3f} pf={after['profit_factor']:.2f} "
            f"E[R]={after['expectancy_r']:+.4f} ret={after['total_return']:+.3f} "
            f"dd={after['max_drawdown']:.3f} sharpe={after['sharpe']:+.2f}"
        )
    print(json.dumps(significance, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
