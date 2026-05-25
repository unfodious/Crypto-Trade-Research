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

## Safety Boundary

All model outputs are research signals until a separate promotion issue defines the integration contract, paper-trading evidence, rollback plan, and runtime safety gates. The live `crypto-trade` runtime remains the source of truth for account state, order placement, leverage, stops, take profit, liquidation handling, and exchange reconciliation.
