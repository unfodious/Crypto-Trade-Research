# Baseline Models

Start with simple baselines. If a simple model cannot beat no-trade and rule-only references out of sample after costs, a deeper model is more likely to overfit than solve the trading problem.

## Current Baselines

- `no_trade`: zero trades, zero exposure.
- `rule_only`: take every candidate setup without an ML filter.
- `linear_probability`: a deterministic threshold model trained only on the time-based training window.

The first implementation is intentionally lightweight and dependency-free. It records the feature list, training/validation/test windows, out-of-sample average R, and feature importance for sanity checks.

## Time-Series Rule

Do not use shuffled cross-validation for performance claims. Split by time:

- train window
- validation window
- test window

Reject a model when edge only exists in the training window.

## Sample Run

```sh
make sample-baselines
```

This writes ignored files under `data/generated/sample_baselines/`.

## When To Try Deep Models

Only consider sequence or deep models after simple baselines show stable out-of-sample expectancy, cost robustness, enough trades, sensible feature importance, and calibration that does not collapse by regime.
