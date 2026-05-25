.PHONY: install test lint format check sample-dataset sample-features sample-labels sample-backtest sample-baselines

install:
	uv sync --extra dev --extra research

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test

sample-dataset:
	uv run crypto-trade-ingest-market-dataset \
		--source-csv tests/fixtures/ingestion_source/market_candles.csv \
		--output-dir data/generated \
		--dataset-name sample_market_dataset \
		--generator-version local.sample.v1 \
		--generated-at 2026-05-25T00:00:00Z

sample-features:
	uv run python scripts/generate_sample_features.py \
		--source-csv tests/fixtures/ingestion_source/market_candles.csv \
		--output-dir data/generated/sample_features \
		--feature-set-version features.sample.v1 \
		--rolling-window 2

sample-labels:
	uv run python scripts/generate_sample_labels.py \
		--source-csv tests/fixtures/ingestion_source/market_candles.csv \
		--output-dir data/generated/sample_labels \
		--label-set-version labels.sample.v1 \
		--horizon-bars 2 \
		--side long \
		--stop-loss-pct 0.02 \
		--target-pct 0.04 \
		--cost-pct 0.001 \
		--flat-threshold-pct 0.001

sample-backtest:
	uv run python scripts/generate_sample_backtest.py \
		--output-dir data/generated/sample_backtest

sample-baselines:
	uv run python scripts/generate_sample_baselines.py \
		--output-dir data/generated/sample_baselines
