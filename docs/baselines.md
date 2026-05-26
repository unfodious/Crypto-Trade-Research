# Baseline Models

Start with simple baselines. If a simple model cannot beat no-trade and rule-only references out of sample after costs, a deeper model is more likely to overfit than solve the trading problem.

## Current Baselines

- `no_trade`: zero trades, zero exposure.
- `rule_only`: take every candidate setup without an ML filter.
- `linear_probability`: a deterministic threshold model trained only on the time-based training window.
- `multifeature_ridge`: a dependency-free multifeature ridge-probability baseline. It standardizes
  features on the train window, imputes missing feature values to train means, fits a regularized
  linear probability proxy, converts scores through a sigmoid, and calibrates its take threshold on
  validation only.

The implementation is intentionally lightweight and dependency-free. It records the feature list,
training/validation/test windows, out-of-sample average R, and feature importance for sanity checks.

Generated reports expose both scopes:

- `*_oos`: validation + test only; use these for promotion or rejection evidence.
- non-`*_oos`: train + validation + test combined; use these only as diagnostics.

## Time-Series Rule

Do not use shuffled cross-validation for performance claims. Split by time:

- train window
- validation window
- test window

Reject a model when edge only exists in the training window.

## Multifeature Rules

The multifeature baseline is meant to answer whether the enriched feature library contains useful
combined information before introducing heavier model dependencies.

Guardrails:

- train statistics come from the train split only,
- validation chooses the probability threshold,
- test data is never used for fitting or calibration,
- feature importance is diagnostic, not proof of causality,
- missing feature values fail soft inside research by using train means; runtime artifacts still
  fail closed until a promoted model contract explicitly supports imputation.

## Sample Run

```sh
make sample-baselines
```

This writes ignored files under `data/generated/sample_baselines/`.

## When To Try Deep Models

Only consider sequence or deep models after simple baselines show stable out-of-sample expectancy, cost robustness, enough trades, sensible feature importance, and calibration that does not collapse by regime.
