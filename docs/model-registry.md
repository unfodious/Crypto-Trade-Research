# Model Registry

Crypto Trade research uses a simple local JSON registry before considering heavier tracking services.

## Record Shape

Each experiment writes one `record.json` under:

```text
data/generated/experiment_registry/<model_id>/<version>/record.json
```

The record must include:

- model id, version, and model type
- research repo git commit
- dataset manifest path and version
- feature list and feature code version
- label config
- train, validation, and test windows
- fee, slippage, and funding assumptions
- model, baseline, walk-forward, and drawdown metrics
- walk-forward report path
- explicit promotion or rejection decision with gate results

## Promotion Gates

A model can only be marked `promote_to_paper_trading` when all gates pass:

- model average R beats rule-only and naive baselines out of sample after costs
- walk-forward average R is positive
- drawdown depth and duration are within configured limits
- feature leakage checks pass
- stability checks do not show a single fragile parameter optimum
- paper-trading plan path is attached

Failed gates produce a `reject` decision with reviewable reasons.

## Commands

Generate deterministic sample records:

```sh
make sample-experiment-registry
```

List records and their promoted/rejected status:

```sh
uv run crypto-trade-experiments list \
  --registry-dir data/generated/experiment_registry
```

## Retention

Commit only the registry code, docs, and tiny fake fixtures. Do not commit local registry outputs,
private datasets, trained model binaries, notebooks with private exports, production account data,
credentials, or generated reports. Keep them under ignored paths such as `data/`, `datasets/`,
`artifacts/`, `models/`, `reports/`, and `mlruns/`.
