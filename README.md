# Crypto Trade Research

Research-only Python workspace for the Crypto Trade ML and meta-strategy pipeline.

This repository is intentionally separate from `crypto-trade`, the Go runtime that owns exchange integration, account state, fake/live executors, and production risk gates. Research code here may produce datasets, feature definitions, labels, model artifacts, evaluation reports, and integration contracts, but it must not place, cancel, or modify live orders.

## Current Scope

- Define reproducible research project structure.
- Capture market-data and research-run contracts.
- Provide smoke tests, linting, formatting, and documentation entry points.
- Keep private datasets, credentials, experiment outputs, and model artifacts out of git by default.

## Non-Goals

- No live trading integration.
- No production order/executor changes.
- No direct neural-network trading decisions.
- No model promotion without explicit out-of-sample, walk-forward, paper-trading, and safety-gate evidence.

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

- `src/crypto_trade_research/data/`: dataset ingestion and versioning code.
- `src/crypto_trade_research/features/`: regime, indicator, price-action, volatility, participation, and multi-timeframe features.
- `src/crypto_trade_research/labels/`: target-before-stop, R multiple, MFE/MAE, forward-return, and no-trade labels.
- `src/crypto_trade_research/backtest/`: walk-forward and research backtest loops.
- `src/crypto_trade_research/models/`: supervised baselines and later experimental model families.
- `src/crypto_trade_research/evaluation/`: expectancy, drawdown, turnover, exposure, and sensitivity metrics.
- `src/crypto_trade_research/reporting/`: reproducible reports for promotion review.
- `docs/`: architecture, data contracts, and experiment guidelines.
- `notebooks/`: exploratory notebooks only; durable logic should move into `src/`.

## Safety Boundary

All model outputs are research signals until a separate promotion issue defines the integration contract, paper-trading evidence, rollback plan, and runtime safety gates. The live `crypto-trade` runtime remains the source of truth for account state, order placement, leverage, stops, take profit, liquidation handling, and exchange reconciliation.
