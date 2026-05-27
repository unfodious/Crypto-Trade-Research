# CT-171 Historical Holdout Replay Cache

Status: implemented.

CT-170 cached the generated CT-169 feature frame, but a cache-hit replay still took about `340s`
because it had to read the full 1GB feature parquet, load source OHLCV for labels and entry prices,
and rescore/rank every pack. CT-171 adds a second-stage per-pack replay cache.

## Implementation

- Added `replay_cache_dir` to `configs/ct169-older-holdout-replay.json`.
- Added `research.historical-holdout-pack-replay-cache.v1` artifacts:
  - `manifest.json`;
  - `replay.json`.
- Pack replay cache key includes:
  - CT-170 feature cache key;
  - pack manifest path and digest;
  - model artifact digest;
  - issue/epic IDs.
- If all requested pack replay caches exist, the runner writes the normal replay report from cached
  replay payloads without loading full source/funding/feature parquet rows.
- Replay reports now include `replay_cache.status` and cache keys.

The cache stores research replay outputs only. It has no live trading authority and does not touch
runtime order placement.

## Verification

Unit/local:

```sh
.venv/bin/python -m pytest tests/test_historical_holdout_replay.py
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Results:

- `118 passed`;
- `ruff check .` passed;
- `ruff format --check .` passed.

Real CT-169 replay:

First run after CT-171:

- `feature_cache.status = "hit"`;
- `replay_cache.status = "miss"`;
- wall time about `339.55s`;
- wrote pack replay cache for both CT-145 and CT-156.

Second run:

- `feature_cache.status = "hit"`;
- `replay_cache.status = "hit"`;
- wall time about `0.31s`.

Metrics remained unchanged:

| Candidate | Trades | Avg R | Max DD |
| --- | ---: | ---: | ---: |
| CT-145 no-TON | 1,255 | 0.0287 | 4.34% |
| CT-156 high-beta + DOT | 672 | 0.0716 | 8.32% |

## Residual

The fast path is valid for repeated runs with unchanged dataset/funding/feature/pack/model inputs.
Any change to those inputs intentionally invalidates the replay cache and returns to the full replay
path once.
