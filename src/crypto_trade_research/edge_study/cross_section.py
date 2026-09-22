"""Cross-sectional relative-strength study: rank the universe, long top / short bottom.

Research only. No exchange client, no credentials, no order path.

Why this is a different hypothesis, not a variation
---------------------------------------------------

`docs/research/edge-study-4h-2026-09-22.md` asked "is the direction of this pair
predictable?" and answered no. It also found that the one positive slice -
shorts, +0.056 R against longs -0.007 R - sat in a window where buy-and-hold lost
23.5%. That is market beta wearing a strategy's clothes.

This study asks a question that beta cannot answer: **given 11 correlated perps,
is the RELATIVE ordering between them predictable even when the absolute
direction is not?** Every rebalance takes `top_k` longs and `top_k` shorts with
equal risk per leg, so the market factor cancels by construction and a positive
result cannot be beta.

Mechanics, all reusing the directional study's parts
-----------------------------------------------------

- **Candidates.** Every pair, every 4h bar (or every `stride_bars`), both sides.
  No entry rule: the ranking IS the entry rule, which is the point.
- **Labels.** `labels.label_setups`, unchanged: triple barrier on the 1m path,
  stop 1.5 ATR, target 3.0 ATR, 30-bar horizon, ties resolved as the stop.
- **Target.** Not "did this pair hit its target" but "did this pair's long leg
  beat the cross-sectional median of the pairs quoted at the same instant". A
  relative label for a relative question.
- **Model inputs.** Each feature is replaced by its cross-sectional rank at that
  instant, mapped to [-1, +1]. A model fed raw levels would relearn the market
  factor; ranks within a bar cannot contain it.
- **Evaluation.** `walkforward.run_walk_forward`, unchanged: expanding windows,
  purged on `exit_time`, 7-day embargo.
- **Costs.** `costs.CostModel` and `backtest.simulate`, unchanged, applied to
  BOTH legs of every rebalance.
- **Benchmark.** A random ranking over the same bars with the same `top_k`, so
  it has the same trade count and the same turnover, plus equal-weight
  buy-and-hold.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_trade_research.edge_study import altdata as alt_data
from crypto_trade_research.edge_study import backtest as bt
from crypto_trade_research.edge_study import data as market
from crypto_trade_research.edge_study import features as feat
from crypto_trade_research.edge_study import labels as lab
from crypto_trade_research.edge_study.costs import CostModel
from crypto_trade_research.edge_study.labels import BarrierConfig, barrier_prices

LOGGER = logging.getLogger(__name__)

CROSS_PREFIX = "cs_"


@dataclass(frozen=True)
class CrossSectionConfig:
    """Portfolio shape for the ranked book."""

    top_k: int = 3
    stride_bars: int = 1
    min_pairs_per_bar: int = 6


DEFAULT_CROSS_SECTION = CrossSectionConfig()


def _side_setups(
    features: pd.DataFrame, side: int, config: BarrierConfig, stride: int
) -> pd.DataFrame:
    """Every bar is a candidate on `side`; the ranking decides which are taken."""
    eligible = features[features["atr"].notna() & (features["atr"] > 0)]
    if stride > 1:
        eligible = eligible.iloc[::stride]
    if eligible.empty:
        return pd.DataFrame()
    entry = eligible["close"].to_numpy(dtype=float)
    atr_values = eligible["atr"].to_numpy(dtype=float)
    stops, targets = zip(
        *(barrier_prices(e, side, a, config) for e, a in zip(entry, atr_values, strict=True)),
        strict=True,
    )
    return pd.DataFrame(
        {
            "decision_time": eligible["decision_time"].to_numpy(),
            "bar_time": eligible.index,
            "side": side,
            "family": "cross_section",
            "entry_price": entry,
            "atr": atr_values,
            "stop_price": np.asarray(stops, dtype=float),
            "target_price": np.asarray(targets, dtype=float),
        }
    )


def build_panel(
    universe: tuple[str, ...],
    archive: Path,
    start: str,
    end: str,
    config: BarrierConfig,
    cache_dir: Path | None,
    alt_cache_dir: Path | None,
    stride: int = 1,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Label the long and short leg of every pair at every rebalance instant.

    Returns one frame holding both sides. The long rows carry the features the
    ranking model sees; the short rows exist so the bottom of the ranking can be
    executed with the same geometry and the same cost treatment.
    """
    btc = market.load_pair("BTCUSDT", archive, start, end, cache_dir=cache_dir)
    bars_by_pair: dict[str, pd.DataFrame] = {}
    frames: list[pd.DataFrame] = []

    for pair in universe:
        pair_data = (
            btc
            if pair == "BTCUSDT"
            else market.load_pair(pair, archive, start, end, cache_dir=cache_dir)
        )
        panels = (
            None if alt_cache_dir is None else alt_data.load_panels(pair, start, end, alt_cache_dir)
        )
        features = feat.build_features(
            pair_data.bars["4h"], pair_data.bars["1D"], btc.bars["1D"], panels
        )
        bars_by_pair[pair] = pair_data.bars["4h"]
        context = features.reset_index(names="bar_time")
        columns = ["bar_time", *[c for c in feat.FEATURE_COLUMNS if c in context.columns]]

        for side in (1, -1):
            candidates = _side_setups(features, side, config, stride)
            if candidates.empty:
                continue
            candidates = candidates.merge(context[columns], on="bar_time", how="left")
            labelled = lab.label_setups(candidates, pair_data.minute, config)
            if labelled.empty:
                continue
            labelled["pair"] = pair
            frames.append(labelled)
        LOGGER.info("%s: cross-section panel built", pair)

    panel = pd.concat(frames, ignore_index=True).sort_values(["decision_time", "pair", "side"])
    return panel.reset_index(drop=True), bars_by_pair


def cross_sectional_ranks(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Replace each feature by its within-bar rank, mapped to [-1, +1].

    Done per `decision_time`, so the transform uses only rows quoted at the same
    instant and can never reach across time. The market factor - the component
    every pair shares at that instant - is removed by construction, which is the
    whole reason to rank rather than to standardise over history.
    """
    ranked = frame.copy()
    grouped = frame.groupby("decision_time", sort=False)
    for column in columns:
        ranks = grouped[column].rank(pct=True, method="average")
        ranked[f"{CROSS_PREFIX}{column}"] = (ranks - 0.5) * 2.0
    return ranked


def relative_labels(longs: pd.DataFrame, min_pairs: int) -> pd.DataFrame:
    """`win` = this pair's long leg beat the median long leg at the same instant.

    Bars quoting fewer than `min_pairs` pairs are dropped: a "cross-section" of
    three names is not one, and those bars are exactly where a thin universe
    would manufacture an apparent edge.
    """
    counts = longs.groupby("decision_time")["pair"].transform("size")
    usable = longs[counts >= min_pairs].copy()
    if usable.empty:
        return usable

    # Realized R alone ties badly: 62% of setups exit exactly at the stop, so
    # `gross_r == -1.0` for most of a bar's cross-section and a plain
    # "above the median" label degenerates (it measured a 26% base rate in
    # testing, not 50%). MFE breaks those ties on the evidence the labeller
    # already records: among pairs that all stopped out, the one that ran
    # furthest in favour first was the relatively stronger name. The
    # coefficient is small enough that MFE can never outrank realized R.
    score = usable["gross_r"] + 1e-6 * usable["mfe_r"].fillna(0.0)
    usable["relative_score"] = score
    ranks = usable.groupby("decision_time")["relative_score"].rank(pct=True, method="average")
    usable["directional_win"] = usable["win"]
    usable["win"] = (ranks > 0.5).astype(int)
    return usable


def _legs(
    predictions: pd.DataFrame,
    shorts_by_key: pd.DataFrame,
    config: CrossSectionConfig,
    score_column: str,
) -> pd.DataFrame:
    """Turn per-bar scores into an equal-count long/short book.

    Top `top_k` scores are taken with their own long rows; bottom `top_k` are
    taken with the SHORT row for the same pair and bar. Equal counts and equal
    risk per leg is what makes the book market-neutral: the shared market move
    enters both legs with opposite sign and cancels before costs.
    """
    long_rows: list[pd.DataFrame] = []
    short_rows: list[pd.DataFrame] = []
    for _, group in predictions.groupby("decision_time", sort=False):
        if len(group) < 2 * config.top_k:
            continue
        ordered = group.sort_values(score_column, ascending=False)
        long_rows.append(ordered.head(config.top_k))
        short_rows.append(ordered.tail(config.top_k))
    if not long_rows:
        return pd.DataFrame()

    longs = pd.concat(long_rows, ignore_index=True)
    shorts_selection = pd.concat(short_rows, ignore_index=True)[["decision_time", "pair", "fold"]]
    shorts = shorts_selection.merge(shorts_by_key, on=["decision_time", "pair"], how="inner")
    book = pd.concat([longs, shorts], ignore_index=True)
    return book.sort_values("decision_time").reset_index(drop=True)


def build_book(
    predictions: pd.DataFrame,
    shorts: pd.DataFrame,
    config: CrossSectionConfig,
    score_column: str = "probability",
) -> pd.DataFrame:
    """The executed long/short book for a set of scored out-of-sample rows."""
    carried = shorts.drop(columns=["fold", "probability", "selected"], errors="ignore")
    return _legs(predictions, carried, config, score_column)


def random_books(
    predictions: pd.DataFrame,
    shorts: pd.DataFrame,
    config: CrossSectionConfig,
    seeds: int = 5,
) -> list[pd.DataFrame]:
    """Random rankings over the identical bars: same book size, same turnover.

    This is the benchmark that matters here. Random ENTRY (the directional
    study's benchmark) is not a fair comparison for a ranked book, because a
    market-neutral book's return distribution is not the directional one. A
    random RANKING trades the same instruments at the same instants in the same
    quantity and differs only in the ordering, which is precisely the thing
    being tested.
    """
    books: list[pd.DataFrame] = []
    for seed in range(seeds):
        rng = np.random.default_rng(4242 + seed * 131)
        shuffled = predictions.copy()
        shuffled["random_score"] = rng.random(len(shuffled))
        book = build_book(shuffled, shorts, config, score_column="random_score")
        if not book.empty:
            books.append(book)
    return books


def net_r(trades: pd.DataFrame, costs: CostModel) -> np.ndarray:
    if trades.empty:
        return np.array([])
    _, priced, _ = bt.simulate(trades, costs)
    return priced["net_r"].to_numpy(dtype=float) if not priced.empty else np.array([])
