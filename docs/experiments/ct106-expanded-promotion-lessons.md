# CT-106 Expanded Promotion Workflow Lessons

Date: 2026-05-26

## Final CT-96 Outcome

CT-96 did not produce a promoted paper-trading candidate.

The expanded dataset and promotion workflow were still useful because they turned a promising
one-day CT-93 rejection path into a clearer rejection:

- CT-99 confirmed the expanded dataset quality and fixed cross-symbol feature/label boundary bugs.
- CT-100 added batch experiment and leaderboard support.
- CT-101 rejected the expanded high-range short-fade threshold family.
- CT-102 rejected complementary setup and label variants.
- CT-103 added stability, sensitivity, and drawdown gates.
- CT-104 blocked candidate selection.
- CT-105 blocked paper-pack preparation.

## Durable Lessons

- A model that beats rule-only can still be rejected if both are negative after costs.
- A paper-trading pack must not exist for a rejected candidate.
- Stability gates should block candidates with isolated day, symbol, session, or nearby-threshold
  pockets.
- Generated private datasets, Parquet files, model artifacts, registry records, and leaderboards
  stay under ignored `data/generated/` paths.
- Real promotion evidence must be generated in a container with `git` installed. Artifacts with
  `research_git_commit: unknown` are rejected local evidence only.
- Do not widen CT-101/CT-102 threshold grids against the same test window unless a future task first
  changes the setup thesis or risk model for a pre-stated reason.

## Reusable Commands

Run CT-101 expanded short-fade matrix:

```sh
uv run crypto-trade-run-batch-experiments \
  --matrix configs/ct101-short-fade-expanded-matrix.json
```

Run CT-102 complementary matrix:

```sh
uv run crypto-trade-run-batch-experiments \
  --matrix configs/ct102-complementary-expanded-matrix.json
```

Docker command for promotion-grade reruns that need exact git metadata:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'apt-get update >/tmp/apt.log && apt-get install -y git >/tmp/git.log && python -m pip install -e ".[dev]" >/tmp/pip.log && crypto-trade-run-batch-experiments --matrix configs/ct102-complementary-expanded-matrix.json'
```

Close-out verifier:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'python -m pip install -e ".[dev]" >/tmp/pip.log && python -m pytest && ruff check . && ruff format --check .'
```
