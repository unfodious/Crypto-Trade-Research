# ML Research Framework Operational Audit

Date: 2026-05-26
Scope: `crypto-trade-research` after removing the legacy Go neural model from `crypto-trade`.

## Summary

`crypto-trade-research` is a research scaffold, not a promoted market model. It can ingest
contract-shaped market candle CSV data, generate point-in-time OHLCV features, generate
after-the-fact labels, evaluate signal outcomes, compare simple baselines, apply a meta-strategy
filter, validate an inference contract, and record promotion decisions.

The repository is ready for the next step: connect real Binance historical data exports to the
research data contract and run a first real baseline experiment. It is not yet ready to produce a
live-trading model artifact because the real-data training command, artifact persistence, and
promotion evidence are not implemented end to end.

## What Exists

- Dataset ingestion: `src/crypto_trade_research/data/ingestion.py` validates a strict
  `research.dataset.v1` candle CSV and writes raw/clean Parquet plus a manifest.
- Feature engineering: `src/crypto_trade_research/features/core.py` builds point-in-time OHLCV,
  price-action, rolling, participation, and optional higher-timeframe features.
- Labels: `src/crypto_trade_research/labels/outcomes.py` creates leakage-separated outcome labels
  with stop/target handling and R-multiple fields.
- Backtest/evaluation: `src/crypto_trade_research/backtest/walk_forward.py` evaluates signal rows
  with cost assumptions, drawdown, exposure, turnover, and concurrency metrics.
- Baselines: `src/crypto_trade_research/models/baselines.py` trains and evaluates a deterministic
  `linear_probability` baseline against `no_trade` and `rule_only`.
- Meta-strategy: `src/crypto_trade_research/meta_strategy.py` turns deterministic candidate setups
  plus model estimates into take/skip decisions under risk gates.
- Registry: `src/crypto_trade_research/tracking/registry.py` stores experiment metadata and
  promotion/rejection decisions.
- Inference contract: `src/crypto_trade_research/inference_contract.py` validates
  `ml-inference.v1` request/response payloads and forbids model-owned leverage, size, quantity, or
  notional fields.

## Gaps

### Major: No real historical-data export adapter

The Go backend stores useful futures candles in `historical_candles`, but the research repo only
accepts contract-shaped CSV inputs. There is no committed exporter that transforms backend
PostgreSQL candles into `research.dataset.v1` CSV with `venue`, `market_type`, `source_available_at`,
source metadata, and checksum fields.

Expected next step: add an explicit export path from backend `historical_candles` or a separate
research-side importer that reads a safe DB/export file and writes the ingestion CSV contract.

### Major: No real experiment runner over dataset + features + labels

The repository has sample generators and library functions, but no single command that takes a real
dataset manifest, creates features/labels, joins them leakage-safely, trains baselines, evaluates
walk-forward splits, and writes a registry record.

Expected next step: add a `crypto-trade-run-baseline-experiment` command or script that produces a
complete report under ignored `reports/` or `data/generated/`.

### Major: No promoted model artifact format yet

The registry records experiment decisions, but no model artifact format is committed for a trained
baseline or future model. `ml-inference.v1` describes runtime recommendations, not how a trained
artifact is serialized, loaded, versioned, or served.

Expected next step: define the first artifact type for `linear_probability` or a scikit-learn
baseline, including feature schema, preprocessing, thresholds, calibration metadata, and hash.

### Normal: Sample fixtures prove mechanics, not edge

Current sample outputs are deterministic fake fixtures. They are valuable for smoke tests and agent
orientation, but they cannot answer whether a strategy has edge on crypto markets.

Expected next step: run the same pipeline on real Binance USD-M Futures historical data with
realistic fee/slippage/funding assumptions.

## Recommended Next Experiment

Use the already downloaded futures candles from `crypto-trade` backtests as the first real dataset,
but export them into the research contract instead of training inside the Go runtime.

Minimum experiment:

1. Export one symbol, for example `BTCUSDT`, from `historical_candles` for `market_type=um_futures`.
2. Include at least `1m`, `15m`, and `1h` candles if multi-timeframe features are tested.
3. Ingest the export with `crypto-trade-ingest-market-dataset`.
4. Generate features with a fixed feature-set version.
5. Generate labels with explicit stop, target, horizon, costs, and `stop_first` ambiguity handling.
6. Train/evaluate `no_trade`, `rule_only`, and `linear_probability` baselines on time splits.
7. Record the experiment as `reject` unless out-of-sample metrics beat rule-only after costs and
   pass drawdown/stability gates.

## Verification

Use:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Docker fallback:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'python -m pip install -e ".[dev]" && python -m pytest && ruff check . && ruff format --check .'
```

