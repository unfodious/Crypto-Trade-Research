# Crypto Trade Research

Research-only Python workspace for the Crypto Trade ML and meta-strategy pipeline.

This repository is intentionally separate from `crypto-trade-infrastructure` and the Go `crypto-trade` backend. Research code here may produce datasets, feature definitions, labels, model artifacts, evaluation reports, and integration contracts, but it must not place, cancel, or modify live orders. The Go backend remains responsible for runtime execution, exchange integration, account state, risk gates, and live trading safety.

See YouTrack epic `CT-34` for the implementation roadmap.

## Initial Direction

- Build reproducible market datasets.
- Engineer market-regime, price-action, indicator, volatility, participation, and multi-timeframe features.
- Create leakage-safe labels such as target-before-stop, expected R, MFE/MAE, and no-trade outcomes.
- Evaluate simple non-neural baselines before deep learning.
- Promote models only after out-of-sample, walk-forward, paper-trading, rollback, and safety-gate evidence.

## Current Scope

- Define reproducible research project structure.
- Capture market-data and research-run contracts.
- Provide smoke tests, linting, formatting, and documentation entry points.
- Keep private datasets, credentials, experiment outputs, and model artifacts out of git by default.

## Non-Goals

- No live trading integration.
- No production order/executor changes.
- No direct neural-network trading decisions.
- No secrets, API keys, raw credentials, or private production exports committed here.
- No direct model authority over leverage, order size, or order submission.

## Setup

Install `uv`, then run:

```sh
uv sync --extra dev --extra research
```

Run the validation checks:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

If `uv` is not available on a host, a Docker check can be used for the current lightweight scaffold:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'python -m pip install -e ".[dev]" && python -m pytest && ruff check . && ruff format --check .'
```

## Repository Map

- `schemas/`: canonical dataset schema helpers and fixture validation.
- `src/crypto_trade_research/data/`: dataset ingestion and versioning code.
- `src/crypto_trade_research/features/`: regime, indicator, price-action, volatility, participation, and multi-timeframe features.
- `src/crypto_trade_research/labels/`: target-before-stop, R multiple, MFE/MAE, forward-return, and no-trade labels.
- `src/crypto_trade_research/backtest/`: walk-forward and research backtest loops.
- `src/crypto_trade_research/models/`: supervised baselines and later experimental model families.
- `src/crypto_trade_research/tracking/`: JSON experiment registry and promotion gates.
- `src/crypto_trade_research/inference_contract.py`: research-to-runtime inference contract validation.
- `src/crypto_trade_research/evaluation/`: expectancy, drawdown, turnover, exposure, and sensitivity metrics.
- `src/crypto_trade_research/reporting/`: reproducible reports for promotion review.
- `tests/fixtures/`: fake committed datasets for schema and smoke tests.
- `docs/`: architecture, data contracts, and experiment guidelines.
- `notebooks/`: exploratory notebooks only; durable logic should move into `src/`.

## Dataset Generation

Generate the tiny deterministic sample dataset from committed fake fixtures:

```sh
make sample-dataset
```

The command writes ignored local outputs under `data/generated/sample_market_dataset/`:

- `raw/market_candles.parquet`
- `clean/market_candles.parquet`
- `manifest.json`

Equivalent direct command:

```sh
uv run crypto-trade-ingest-market-dataset \
  --source-csv tests/fixtures/ingestion_source/market_candles.csv \
  --output-dir data/generated \
  --dataset-name sample_market_dataset \
  --generator-version local.sample.v1 \
  --generated-at 2026-05-25T00:00:00Z
```

Only tiny fake fixtures belong in git. Large raw exports, cleaned Parquet datasets, private production extracts, and generated reports stay under ignored local paths such as `data/`, `datasets/`, `artifacts/`, and `reports/`.

## Feature Generation

Generate sample OHLCV features from the fake fixture:

```sh
make sample-features
```

The command writes ignored local outputs under `data/generated/sample_features/`:

- `features.parquet`
- `feature_manifest.json`

The first feature slice is deterministic and point-in-time. Warmup rows use `None` where a lookback is not yet available, and higher-timeframe joins must satisfy `source_available_at <= decision_time`.

## Label Generation

Generate sample after-the-fact trade labels from the fake fixture:

```sh
make sample-labels
```

The command writes ignored local outputs under `data/generated/sample_labels/`:

- `labels.parquet`
- `label_manifest.json`

Labels intentionally use future windows and must stay separate from feature generation. Join labels to features only by stable keys such as venue, market type, symbol, timeframe, and decision time.

## Backtest Evaluation

Generate a deterministic sample research backtest:

```sh
make sample-backtest
```

The command writes ignored local outputs under `data/generated/sample_backtest/`:

- `report.json`
- `trades.parquet`
- `equity_curve.parquet`
- `report.md`

Backtests are rejection evidence and research diagnostics, not proof of live profitability.

## Baseline Models

Generate a deterministic baseline comparison:

```sh
make sample-baselines
```

The command writes ignored local outputs under `data/generated/sample_baselines/`:

- `baseline_report.json`
- `baseline_report.md`

The baseline layer compares no-trade, rule-only, and simple linear-probability filtering before any sequence/deep model is considered.

## Baseline Experiment Runner

Run the end-to-end baseline experiment runner from a JSON config:

```sh
make sample-baseline-experiment
```

The sample command uses `configs/sample-baseline-experiment.json` and writes ignored outputs under
`data/generated/sample_baseline_experiment/` plus an experiment registry record under
`data/generated/experiment_registry/`. For real data, point `source_csv` at the backend
`research.dataset.v1` export or set `dataset_manifest_path` to an already ingested dataset manifest.
Splits must stay chronological; shuffled split configs are rejected.

## Batch Experiment Runner

Run a reproducible matrix of baseline experiment configs and write a leaderboard:

```sh
make sample-batch-experiments
```

The sample command uses `configs/sample-batch-experiments.json` and writes ignored outputs under
`data/generated/sample_batch_experiments/`. Each matrix item points at a normal baseline experiment
config. One failed experiment is recorded as a failed leaderboard row without deleting completed
registry outputs from other configs.

Direct command:

```sh
uv run crypto-trade-run-batch-experiments \
  --matrix configs/sample-batch-experiments.json
```

Leaderboard rows include decision, failed gates, model/rule out-of-sample average R, trade count,
max drawdown, symbol coverage, artifact hash, and registry path.

## Meta-Strategy

Generate a deterministic candidate setup → take/skip/size report:

```sh
make sample-meta-strategy
```

The command writes ignored local outputs under `data/generated/sample_meta_strategy/`:

- `meta_strategy_report.json`
- `meta_strategy_report.md`

The meta-strategy layer keeps candidate generation and risk sizing deterministic. ML estimates can filter setups, but they do not directly set leverage.

## Model Registry

Generate deterministic sample experiment records:

```sh
make sample-experiment-registry
```

List experiment records and promoted/rejected status:

```sh
uv run crypto-trade-experiments list \
  --registry-dir data/generated/experiment_registry
```

The command writes ignored local outputs under `data/generated/experiment_registry/`. Each `record.json` captures model version, git commit, dataset manifest, feature and label metadata, train/validation/test windows, cost assumptions, metrics, walk-forward report path, and an explicit promotion or rejection decision.

## Model Artifacts

The initial trained-model artifact format is `crypto-trade.model-artifact.v1`, implemented in
`crypto_trade_research.models.artifacts`. It writes hashed JSON artifacts for simple
`linear_probability_threshold` candidates, validates feature schema compatibility on load, rejects
credential-like or direct order-authority fields, and exposes prediction output only as `take` or
`skip`.

## Inference Contract

Validate example research-to-runtime inference fixtures:

```sh
uv run pytest tests/test_inference_contract.py
```

The `ml-inference.v1` contract supports model estimates and `take`/`skip` recommendations only. It explicitly forbids ML-owned leverage, order size, quantity, or notional fields; runtime risk gates remain outside this repository.

## Paper-Trading Safety Plan

Validate the ML promotion checklist template:

```sh
uv run pytest tests/test_promotion_checklist.py
```

The checklist defines the required rollout path: research-only, fake executor replay, paper-trading dry-run, shadow mode, and only then a separately approved tiny-size pilot.

## Framework Feasibility

The current recommendation is documented in `docs/framework-feasibility.md`: keep the local pipeline as primary, evaluate vectorbt/forecasting tools only as adapters or benchmarks, and defer RL frameworks until the fake/paper environment is realistic.

## End-to-End Runbook

Future agents should start from `docs/end-to-end-ml-research-runbook.md`. It covers setup, sample artifact generation, report interpretation, rejection/promotion rules, troubleshooting, and the CT-34 task map.

## Safety Boundary

All model outputs are research signals until a separate promotion issue defines the integration contract, paper-trading evidence, rollback plan, and runtime safety gates. The live `crypto-trade` runtime remains the source of truth for account state, order placement, leverage, stops, take profit, liquidation handling, and exchange reconciliation.
