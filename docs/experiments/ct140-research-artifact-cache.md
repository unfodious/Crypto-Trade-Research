# CT-140 Research Artifact Cache

Date: 2026-05-27

Issue: CT-140

Epic: CT-113

## Decision

Added a persistent disk-backed artifact cache for research batch runs. This targets the repeated
CT-138/CT-139 pain where Docker restarts lose in-process cache and force six-month feature
generation plus candidate-only label generation to run again.

Redis was not added. For this workload, large parquet-like artifacts are better stored on the
workspace volume than in an in-memory service. Redis can still be useful later for small operational
state such as locks, cursors, queues, or heartbeats.

## What Changed

`crypto_trade_research.experiments.batch` now supports persistent cache artifacts under:

- default: `data/generated/research_cache`
- override: batch matrix field `cache_dir`

Cached artifacts:

- full feature frames used by a batch matrix;
- candidate-only label frames.

Full label frames are not persisted yet because the current CT-113 heavy runs use
`candidate_only` label generation and that is the expensive repeated path.

## Cache Keys

Feature cache keys include:

- source CSV path and hash, when present;
- dataset manifest path and hash;
- funding manifest path and hash;
- dataset name and generator version;
- symbol and timeframe filters;
- feature set version;
- rolling window;
- higher timeframes.

Candidate-label cache keys include all feature-key inputs plus:

- label config;
- candidate setup name;
- candidate setup symbols;
- candidate setup filters.

This keeps point-in-time and leakage assumptions tied to the same inputs that define the research
artifact.

## Behavior

On cache miss:

- compute features or candidate labels;
- write `rows.parquet`;
- write `manifest.json` with cache schema, row count, cache key, and source manifest.

On cache hit:

- read cached parquet rows and manifest;
- skip the expensive feature/label builder;
- log cache hit with row count.

Writes use local temporary files followed by replace, which is sufficient for current single-user
research runs.

## Validation

Added tests that prove:

- a second cache instance can reuse feature and candidate-label artifacts from disk;
- changing candidate setup symbols changes the label cache key.

This is research infrastructure only. It does not touch live trading, order placement, leverage,
margin, or runtime trade state.
