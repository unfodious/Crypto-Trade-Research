QA_IMAGE ?= crypto-trade-research-qa:py312

.PHONY: install test lint format check docker-qa-image docker-test docker-lint docker-format-check docker-qa sample-dataset sample-features sample-labels sample-backtest sample-baselines sample-meta-strategy sample-experiment-registry sample-baseline-experiment sample-batch-experiments

install:
	uv sync --extra dev --extra research

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test

docker-qa-image:
	docker build -f Dockerfile.research-qa -t $(QA_IMAGE) .

docker-test:
	docker run --rm -v "$$PWD":/app -w /app $(QA_IMAGE) python -m pytest

docker-lint:
	docker run --rm -v "$$PWD":/app -w /app $(QA_IMAGE) ruff check .

docker-format-check:
	docker run --rm -v "$$PWD":/app -w /app $(QA_IMAGE) ruff format --check .

docker-qa:
	docker run --rm -v "$$PWD":/app -w /app $(QA_IMAGE) sh -lc 'python -m pytest && ruff check . && ruff format --check .'

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

sample-meta-strategy:
	uv run python scripts/generate_sample_meta_strategy.py \
		--output-dir data/generated/sample_meta_strategy

sample-experiment-registry:
	uv run python scripts/generate_sample_experiment_registry.py \
		--registry-dir data/generated/experiment_registry

sample-baseline-experiment:
	uv run crypto-trade-run-baseline-experiment \
		--config configs/sample-baseline-experiment.json

sample-batch-experiments:
	uv run crypto-trade-run-batch-experiments \
		--matrix configs/sample-batch-experiments.json
