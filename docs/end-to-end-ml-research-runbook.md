# End-to-End ML Research Runbook

YouTrack epic: `CT-34`

This runbook lets a fresh agent restart the ML research workflow without chat memory. It goes from
clone to first baseline report using fake committed fixtures. It does not integrate with live
trading.

## Boundaries

`crypto-trade-research` owns datasets, features, labels, backtests, model experiments, reports,
registry records, and promotion evidence.

`crypto-trade` owns live execution, Binance APIs, account state, risk gates, order placement,
leverage, stops, liquidation handling, reconciliation, operator alerts, and runtime safety.

No live trading integration is allowed without a separate safety-reviewed task.

## Skills To Use

Use these local Crypto Trade skills when relevant:

- `.codex/skills/crypto-trade-strategy-research/`: strategy thesis, validation, model decisions.
- `.codex/skills/crypto-trade-market-regime/`: regime analysis and market state labels.
- `.codex/skills/crypto-trade-price-action/`: OHLCV and setup interpretation.
- `.codex/skills/crypto-trade-indicators/`: indicator selection and leakage checks.
- `.codex/skills/crypto-trade-risk-psychology/`: R multiples, drawdown, exposure, paper gates.
- `.codex/skills/crypto-trade-trading-safety/`: mandatory before any live behavior change.
- `.codex/skills/crypto-trade-qa/`: before closing a task or claiming verification.

## Setup

```sh
cd /Users/unfodious/Projects/crypto-trade-research
uv sync --extra dev --extra research
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Docker fallback:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'python -m pip install -e ".[dev]" && python -m pytest && ruff check . && ruff format --check .'
```

For real experiment evidence that writes model artifacts or registry records, install `git` inside
the Docker container. Records with `research_git_commit: unknown` are acceptable only for rejected
local evidence and block promotion:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'apt-get update >/tmp/apt.log && apt-get install -y git >/tmp/git.log && python -m pip install -e ".[dev]" >/tmp/pip.log && crypto-trade-run-batch-experiments --matrix configs/ct102-complementary-expanded-matrix.json'
```

## Generate The First Research Artifacts

Use the fake committed fixtures to create ignored local outputs:

```sh
make sample-dataset
make sample-features
make sample-labels
make sample-backtest
make sample-baselines
make sample-meta-strategy
make sample-experiment-registry
```

List experiment registry records:

```sh
uv run crypto-trade-experiments list \
  --registry-dir data/generated/experiment_registry
```

## Artifact Map

- Dataset manifest: `data/generated/sample_market_dataset/manifest.json`
- Feature manifest: `data/generated/sample_features/feature_manifest.json`
- Label manifest: `data/generated/sample_labels/label_manifest.json`
- Backtest report: `data/generated/sample_backtest/report.json`
- Baseline report: `data/generated/sample_baselines/baseline_report.json`
- Meta-strategy report: `data/generated/sample_meta_strategy/meta_strategy_report.json`
- Experiment records: `data/generated/experiment_registry/*/*/record.json`

These paths are ignored and must not be committed.

## Interpretation

Start with baselines before advanced models:

1. Compare `no_trade`, `rule_only`, and `linear_probability`.
2. Prefer out-of-sample average R, drawdown, and trade count over win rate.
3. Treat backtests as rejection evidence, not proof of live profitability.
4. Check rejection reasons from the meta-strategy report before increasing model complexity.
5. Record the decision in an experiment registry record.

Reject a model when:

- it fails to beat rule-only and naive baselines out of sample after costs
- walk-forward average R is not acceptable
- drawdown depth or duration exceeds risk limits
- leakage, freshness, or stability checks fail
- results depend on one fragile parameter optimum
- no paper-trading plan exists

Promote only to paper-trading candidate when:

- all promotion gates pass
- `templates/ml-promotion-checklist.v1.json` is completed
- `ml-inference.v1` output contains only take/skip authority
- rollback and kill-switch expectations are documented
- a separate safety-reviewed runtime task exists

## CT-96 Expanded Dataset Outcome

CT-96 expanded the dataset to 90 open days across 11 USD-M futures symbols and produced no promoted
candidate. Use these notes before trying related setup families again:

- Dataset audit: `docs/audit/2026-05-26-ct99-expanded-dataset-quality-audit.md`
- Short-fade rejection: `docs/experiments/ct101-expanded-short-fade-matrix.md`
- Complementary setup rejection: `docs/experiments/ct102-complementary-expanded-matrix.md`
- Stability gates: `docs/experiments/ct103-stability-drawdown-gates.md`
- Selection block: `docs/experiments/ct104-selection-blocked.md`
- Paper pack block: `docs/experiments/ct105-paper-trading-pack-blocked.md`

Do not create a paper-trading pack for rejected candidates. A future promoted candidate must have
positive OOS expectancy after costs, beat rule-only/no-trade, pass drawdown and stability gates,
and capture an exact research git commit in artifact and registry metadata.

## Troubleshooting

If `uv` is missing, use the Docker fallback.

If a report command writes nothing, check that the output path is under `data/generated/` and that
the corresponding source fixture exists under `tests/fixtures/`.

If labels appear in feature rows, stop: this is leakage. Features may only use data available at or
before `decision_time`.

If Docker cannot install packages because of transient SSL/network errors, rerun the same command.

If a model artifact or dataset is large, keep it under ignored paths such as `data/`, `datasets/`,
`artifacts/`, `models/`, `reports/`, or `mlruns/`.

Never print or commit API keys, tokens, encrypted payloads, decrypted credentials, authorization
headers, or production account exports.

## CT-34 Task Map

- `CT-35`: repository scaffold
- `CT-37`: reproducible dataset ingestion/versioning
- `CT-38`: OHLCV feature engineering
- `CT-39`: leakage-safe labels
- `CT-40`: walk-forward evaluation
- `CT-41`: baseline model comparison
- `CT-42`: ML meta-strategy take/skip/size layer
- `CT-43`: model registry and promotion gates
- `CT-44`: inference/export contract
- `CT-45`: paper-trading and safety gate plan
- `CT-46`: advanced framework feasibility
- `CT-47`: this runbook
