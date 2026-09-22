"""Purged, embargoed walk-forward evaluation of a gradient-boosting trade filter.

Why not a single split or shuffled k-fold:

- Shuffled k-fold puts a bar's neighbours (which overlap its barrier window) in
  both train and test. With a 30-bar horizon on 4h data, adjacent labels share
  up to five days of the same price path; k-fold would score a leak.
- A single split gives one number and no sense of its variance across regimes.

So: expanding-window folds ordered in time. For fold k the training set is every
setup whose barrier RESOLVED (`exit_time`) strictly before the test window minus
an embargo. That purges the samples whose outcome window overlaps the test
window and adds a gap on top, so nothing in training can have observed a price
that the test window also depends on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score


@dataclass(frozen=True)
class WalkForwardConfig:
    folds: int = 6
    embargo_days: float = 7.0
    min_train: int = 400
    selectivity: float = 0.5
    random_state: int = 7


DEFAULT_WALK_FORWARD = WalkForwardConfig()


@dataclass(frozen=True)
class Fold:
    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_size: int
    test_size: int
    auc: float
    train_auc: float
    threshold: float


def time_folds(times: pd.Series, folds: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Contiguous, equal-length test windows over the sample's calendar span."""
    start, end = times.min(), times.max()
    edges = pd.date_range(start, end, periods=folds + 1)
    return [(edges[i], edges[i + 1]) for i in range(folds)]


def build_model(config: WalkForwardConfig) -> HistGradientBoostingClassifier:
    """Deliberately small: a few thousand heavily autocorrelated samples cannot
    support a deep ensemble, so depth and leaf count are capped hard."""
    return HistGradientBoostingClassifier(
        max_depth=3,
        max_leaf_nodes=8,
        learning_rate=0.05,
        max_iter=300,
        min_samples_leaf=40,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=config.random_state,
    )


def run_walk_forward(
    samples: pd.DataFrame,
    feature_columns: list[str],
    config: WalkForwardConfig | None = None,
) -> tuple[pd.DataFrame, list[Fold]]:
    """Return the out-of-sample predictions and per-fold diagnostics.

    `samples` must carry `decision_time`, `exit_time`, `win` and the features.
    The returned frame has `probability`, `selected` and `fold` for every test
    row - each produced by a model that never saw that row or its window.
    """
    config = config or DEFAULT_WALK_FORWARD
    samples = samples.sort_values("decision_time").reset_index(drop=True)
    embargo = pd.Timedelta(days=config.embargo_days)
    windows = time_folds(samples["decision_time"], config.folds)

    predictions: list[pd.DataFrame] = []
    diagnostics: list[Fold] = []

    for index, (test_start, test_end) in enumerate(windows):
        is_last = index == len(windows) - 1
        test_mask = (samples["decision_time"] >= test_start) & (
            (samples["decision_time"] <= test_end)
            if is_last
            else (samples["decision_time"] < test_end)
        )
        train_mask = samples["exit_time"] < (test_start - embargo)
        train = samples[train_mask]
        test = samples[test_mask]
        if len(train) < config.min_train or test.empty or train["win"].nunique() < 2:
            continue

        model = build_model(config)
        model.fit(train[feature_columns], train["win"])

        train_probability = model.predict_proba(train[feature_columns])[:, 1]
        # The cutoff is a quantile of the TRAINING distribution, so the test rows
        # never influence how selective the filter is.
        threshold = float(np.quantile(train_probability, 1.0 - config.selectivity))

        probability = model.predict_proba(test[feature_columns])[:, 1]
        fold_predictions = test.copy()
        fold_predictions["probability"] = probability
        fold_predictions["selected"] = probability >= threshold
        fold_predictions["fold"] = index
        predictions.append(fold_predictions)

        auc = (
            float(roc_auc_score(test["win"], probability))
            if test["win"].nunique() > 1
            else float("nan")
        )
        diagnostics.append(
            Fold(
                index=index,
                train_start=train["decision_time"].min(),
                train_end=train["decision_time"].max(),
                test_start=test_start,
                test_end=test_end,
                train_size=len(train),
                test_size=len(test),
                auc=auc,
                train_auc=float(roc_auc_score(train["win"], train_probability)),
                threshold=threshold,
            )
        )

    if not predictions:
        return samples.iloc[0:0].assign(probability=[], selected=[], fold=[]), diagnostics
    return pd.concat(predictions, ignore_index=True), diagnostics
