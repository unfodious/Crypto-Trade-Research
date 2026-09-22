"""End-to-end runner for the 4h/1d non-neural edge study.

Research only: this module reads local candle archives and writes JSON/Markdown.
It has no exchange client, no credentials, and no order path of any kind.

    uv run crypto-trade-run-edge-study --output-dir reports/edge-study
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_trade_research.edge_study import altdata as alt_data
from crypto_trade_research.edge_study import backtest as bt
from crypto_trade_research.edge_study import data as market
from crypto_trade_research.edge_study import features as feat
from crypto_trade_research.edge_study import labels as lab
from crypto_trade_research.edge_study import setups as setup_rules
from crypto_trade_research.edge_study import significance as sig
from crypto_trade_research.edge_study.costs import CostModel
from crypto_trade_research.edge_study.walkforward import WalkForwardConfig, run_walk_forward

LOGGER = logging.getLogger(__name__)

DEFAULT_UNIVERSE = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "DOTUSDT",
    "ATOMUSDT",
    "SUIUSDT",
    "TONUSDT",
    "ICPUSDT",
)

# Widest window for which every pair in the universe has 1m coverage.
DEFAULT_START = "2024-07-01"
DEFAULT_END = "2026-05-24"


def _panels(
    pair: str, start: str, end: str, alt_cache_dir: Path | None
) -> alt_data.AltPanels | None:
    """Non-price panels for one pair, or None when alt data is switched off."""
    if alt_cache_dir is None:
        return None
    return alt_data.load_panels(pair, start, end, alt_cache_dir)


def build_dataset(
    universe: tuple[str, ...],
    archive: Path,
    start: str,
    end: str,
    config: lab.BarrierConfig,
    cache_dir: Path | None,
    alt_cache_dir: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, int]]:
    """Load, feature, generate setups and label every pair."""
    btc = market.load_pair("BTCUSDT", archive, start, end, cache_dir=cache_dir)
    bars_by_pair: dict[str, pd.DataFrame] = {}
    sizes: dict[str, int] = {}
    frames: list[pd.DataFrame] = []

    for pair in universe:
        pair_data = (
            btc
            if pair == "BTCUSDT"
            else market.load_pair(pair, archive, start, end, cache_dir=cache_dir)
        )
        bars_4h = pair_data.bars["4h"]
        bars_by_pair[pair] = bars_4h
        sizes[pair] = len(bars_4h)

        features = feat.build_features(
            bars_4h, pair_data.bars["1D"], btc.bars["1D"], _panels(pair, start, end, alt_cache_dir)
        )
        candidates = setup_rules.generate_setups(features, config)
        if candidates.empty:
            continue
        context = features.reset_index(names="bar_time")
        columns = ["bar_time", *[c for c in feat.FEATURE_COLUMNS if c in context.columns]]
        candidates = candidates.merge(context[columns], on="bar_time", how="left")
        labelled = lab.label_setups(candidates, pair_data.minute, config)
        if labelled.empty:
            continue
        labelled["pair"] = pair
        frames.append(labelled)
        LOGGER.info("%s: %d 4h bars, %d labelled setups", pair, len(bars_4h), len(labelled))

    samples = pd.concat(frames, ignore_index=True).sort_values("decision_time")
    return samples.reset_index(drop=True), bars_by_pair, sizes


def random_benchmark(
    universe: tuple[str, ...],
    archive: Path,
    start: str,
    end: str,
    config: lab.BarrierConfig,
    per_pair_counts: dict[str, int],
    cache_dir: Path | None,
    seeds: int = 5,
) -> list[pd.DataFrame]:
    """Random entries, same ATR geometry, same trade count per pair, N seeds."""
    btc = market.load_pair("BTCUSDT", archive, start, end, cache_dir=cache_dir)
    # Pair loop outside, seed loop inside: each pair's 1m series is read once.
    per_seed: list[list[pd.DataFrame]] = [[] for _ in range(seeds)]
    for pair in universe:
        count = per_pair_counts.get(pair, 0)
        if count <= 0:
            continue
        pair_data = (
            btc
            if pair == "BTCUSDT"
            else market.load_pair(pair, archive, start, end, cache_dir=cache_dir)
        )
        features = feat.build_features(pair_data.bars["4h"], pair_data.bars["1D"], btc.bars["1D"])
        for seed in range(seeds):
            rng = np.random.default_rng(1000 + seed * 97 + hash(pair) % 1000)
            candidates = setup_rules.random_setups(features, config, count, rng)
            if candidates.empty:
                continue
            labelled = lab.label_setups(candidates, pair_data.minute, config)
            if labelled.empty:
                continue
            labelled["pair"] = pair
            per_seed[seed].append(labelled)
    return [
        pd.concat(frames, ignore_index=True).sort_values("decision_time")
        for frames in per_seed
        if frames
    ]


def _breakdown(trades: pd.DataFrame, by: str) -> list[dict[str, object]]:
    """Per-slice expectancy, so a headline number cannot hide on one pair.

    Reported in R per trade (count-independent) both after and before costs,
    which is the only way to compare slices with very different trade counts.
    """
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
        net_r = group["net_r"]
        wins, losses = net_r[net_r > 0], net_r[net_r <= 0]
        rows.append(
            {
                by: str(key),
                "trades": int(len(group)),
                "win_rate": float((net_r > 0).mean()),
                "expectancy_r_after_costs": float(net_r.mean()),
                "expectancy_r_before_costs": float(gross.get(key, float("nan"))),
                "profit_factor_after_costs": (
                    float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf")
                ),
            }
        )
    return rows


def _evaluate(trades: pd.DataFrame, label: str) -> dict[str, object]:
    real, _, _ = bt.simulate(trades, CostModel())
    zero, _, _ = bt.simulate(trades, CostModel.zero())
    return {"label": label, "after_costs": real.to_dict(), "before_costs": zero.to_dict()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Non-neural 4h edge study (research only).")
    parser.add_argument("--archive", type=Path, default=market.DEFAULT_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/edge-study"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/generated/edge-study-cache"))
    parser.add_argument("--alt-cache-dir", type=Path, default=Path("data/generated/altdata-cache"))
    parser.add_argument(
        "--no-alt-data",
        action="store_true",
        help="Run on price-derived features only (the 2026-09-22 baseline).",
    )
    parser.add_argument(
        "--feature-set",
        default="all",
        choices=sorted(feat.FEATURE_SETS),
        help="Which feature block the filter may use: all, price, or alt.",
    )
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--pairs", default=",".join(DEFAULT_UNIVERSE))
    parser.add_argument("--stop-atr", type=float, default=1.5)
    parser.add_argument("--target-atr", type=float, default=3.0)
    parser.add_argument("--horizon-bars", type=int, default=30)
    parser.add_argument("--folds", type=int, default=6)
    parser.add_argument("--embargo-days", type=float, default=7.0)
    parser.add_argument(
        "--selectivity",
        default="0.25,0.5,0.75",
        help="Fractions of candidates the filter is allowed to keep.",
    )
    parser.add_argument("--random-seeds", type=int, default=5)
    parser.add_argument("--report-name", default="edge_study_report.json")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    universe = tuple(pair.strip() for pair in arguments.pairs.split(",") if pair.strip())
    barrier = lab.BarrierConfig(
        stop_atr=arguments.stop_atr,
        target_atr=arguments.target_atr,
        horizon_bars=arguments.horizon_bars,
    )
    output_dir = arguments.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    alt_cache_dir = None if arguments.no_alt_data else arguments.alt_cache_dir
    samples, bars_by_pair, bar_counts = build_dataset(
        universe,
        arguments.archive,
        arguments.start,
        arguments.end,
        barrier,
        arguments.cache_dir,
        alt_cache_dir,
    )
    requested = feat.feature_columns(arguments.feature_set)
    feature_columns = [
        column
        for column in requested
        if column in samples.columns and samples[column].notna().any()
    ]
    usable = samples.dropna(subset=feature_columns).reset_index(drop=True)
    LOGGER.info("samples=%d usable=%d features=%d", len(samples), len(usable), len(feature_columns))

    report: dict[str, object] = {
        "window": {"start": arguments.start, "end": arguments.end},
        "universe": list(universe),
        "bars_4h_per_pair": bar_counts,
        "barrier": asdict(barrier),
        "feature_set": arguments.feature_set,
        "alt_data": not arguments.no_alt_data,
        "feature_columns": feature_columns,
        "costs": asdict(CostModel()),
        "sample_sizes": {
            "setups_labelled": int(len(samples)),
            "setups_usable": int(len(usable)),
            "features": len(feature_columns),
            "per_family": usable.groupby("family").size().to_dict(),
            "per_pair": usable.groupby("pair").size().to_dict(),
            "barrier_distribution": usable.groupby("barrier").size().to_dict(),
            "base_win_rate": float(usable["win"].mean()),
        },
        "evaluations": [],
        "folds": [],
    }

    evaluations: list[dict[str, object]] = [_evaluate(usable, "all_setups")]
    report["breakdowns"] = {
        "by_pair": _breakdown(usable, "pair"),
        "by_family": _breakdown(usable, "family"),
        "by_side": _breakdown(
            usable.assign(side_label=usable["side"].map({1: "long", -1: "short"})), "side_label"
        ),
        "by_quarter": _breakdown(usable, "period"),
    }

    selectivities = [float(value) for value in arguments.selectivity.split(",")]
    for selectivity in selectivities:
        config = WalkForwardConfig(
            folds=arguments.folds,
            embargo_days=arguments.embargo_days,
            selectivity=selectivity,
        )
        predictions, folds = run_walk_forward(usable, feature_columns, config)
        if predictions.empty:
            continue
        selected = predictions[predictions["selected"]]
        evaluations.append(_evaluate(predictions, f"walk_forward_oos_all@{selectivity}"))
        evaluations.append(_evaluate(selected, f"model_filter@{selectivity}"))
        fold_rows = []
        for fold in folds:
            fold_trades = selected[selected["fold"] == fold.index]
            fold_metrics, _, _ = bt.simulate(fold_trades, CostModel())
            fold_rows.append(
                {
                    "selectivity": selectivity,
                    "fold": fold.index,
                    "test_start": str(fold.test_start),
                    "test_end": str(fold.test_end),
                    "train_size": fold.train_size,
                    "test_size": fold.test_size,
                    "auc": fold.auc,
                    "train_auc": fold.train_auc,
                    "selected_trades": int(len(fold_trades)),
                    "metrics_after_costs": fold_metrics.to_dict(),
                }
            )
        report["folds"].extend(fold_rows)

    per_pair_counts = usable.groupby("pair").size().to_dict()
    random_runs = random_benchmark(
        universe,
        arguments.archive,
        arguments.start,
        arguments.end,
        barrier,
        per_pair_counts,
        arguments.cache_dir,
        seeds=arguments.random_seeds,
    )
    random_results = [_evaluate(run, "random_entry") for run in random_runs]
    if random_results:
        evaluations.append(
            {
                "label": "random_entry_mean",
                "after_costs": _mean_metrics([r["after_costs"] for r in random_results]),
                "before_costs": _mean_metrics([r["before_costs"] for r in random_results]),
                "seeds": len(random_results),
            }
        )
        report["random_entry_runs"] = random_results

    report["significance"] = _significance(usable, random_runs)

    hold = bt.buy_and_hold(bars_by_pair)
    evaluations.append(
        {"label": "buy_and_hold", "after_costs": hold.to_dict(), "before_costs": hold.to_dict()}
    )

    report["evaluations"] = evaluations
    report_path = output_dir / arguments.report_name
    report_path.write_text(json.dumps(report, indent=2, default=str))
    LOGGER.info("wrote %s", report_path)
    print(json.dumps(report["sample_sizes"], indent=2, default=str))
    for evaluation in evaluations:
        after = evaluation["after_costs"]
        print(
            f"{evaluation['label']:<34} trades={after['trades']:>5} "
            f"win={after['win_rate']:.3f} pf={after['profit_factor']:.2f} "
            f"ret={after['total_return']:+.3f} ann={after['annualized_return']:+.3f} "
            f"dd={after['max_drawdown']:.3f} sharpe={after['sharpe']:+.2f}"
        )
    return 0


def _net_r(trades: pd.DataFrame, costs: CostModel) -> np.ndarray:
    _, priced, _ = bt.simulate(trades, costs)
    return priced["net_r"].to_numpy(dtype=float) if not priced.empty else np.array([])


def _significance(usable: pd.DataFrame, random_runs: list[pd.DataFrame]) -> dict[str, object]:
    """Block-bootstrap intervals on per-trade R, so a thin mean is not oversold."""
    costs = CostModel()
    sets: dict[str, np.ndarray] = {
        "all_setups": _net_r(usable, costs),
        "breakout_only": _net_r(usable[usable["family"] == setup_rules.BREAKOUT], costs),
        "reversion_only": _net_r(usable[usable["family"] == setup_rules.REVERSION], costs),
    }
    if random_runs:
        sets["random_entry"] = np.concatenate([_net_r(run, costs) for run in random_runs])

    intervals = {name: sig.block_bootstrap_mean(values).to_dict() for name, values in sets.items()}
    result: dict[str, object] = {"per_trade_r_after_costs": intervals}
    if "random_entry" in sets:
        result["rules_minus_random"] = sig.difference_interval(
            sets["all_setups"], sets["random_entry"]
        ).to_dict()
        result["breakout_minus_random"] = sig.difference_interval(
            sets["breakout_only"], sets["random_entry"]
        ).to_dict()
    return result


def _mean_metrics(rows: list[dict[str, float]]) -> dict[str, float]:
    keys = rows[0].keys()
    return {
        key: float(np.mean([row[key] for row in rows if np.isfinite(row[key])])) for key in keys
    }


if __name__ == "__main__":
    raise SystemExit(main())
