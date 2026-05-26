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

## Model Artifact Contract

The first artifact format is JSON with schema version `crypto-trade.model-artifact.v1`. It is
intended for simple `linear_probability_threshold` candidates before any heavier serialization such
as ONNX or pickle is considered.

An artifact must include:

- `model_id`, `model_version`, and `model.model_type`
- linear model parameters: `feature_name`, `threshold`, `positive_direction`, and
  `probability_threshold`
- `feature_schema.feature_set_version` and exact ordered `feature_schema.feature_names`
- preprocessing and calibration metadata
- dataset manifest reference and training data hash
- research git commit and dependency versions
- `created_at`
- `authority.allowed_actions`, which must be only `take` and `skip`
- `artifact_hash`, a SHA-256 of the canonical JSON payload with `artifact_hash=null`

Loaders must fail closed when:

- the artifact schema version is unsupported
- the hash does not match the payload
- required metadata is missing
- the expected feature set version or feature names differ
- a required inference feature is missing
- any credential-like field or direct order authority field is present

Artifacts must not include raw private dataset rows, credentials, exchange keys, order quantities,
notional, leverage, or any field that could directly authorize live execution. The runtime boundary
remains the `ml-inference.v1` contract: a loaded model may recommend only `take` or `skip`; account
state, risk sizing, leverage, stops, take profit, order placement, and kill switches stay outside the
research artifact.
