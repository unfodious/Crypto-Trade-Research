# CT-170 Historical Holdout Feature Cache

Status: implemented.

CT-169 older-holdout replay rebuilt the full `features.ct138.regime-symbol-refinement.v1` frame over
`2,328,480` one-minute rows on every run. CT-170 adds a cache for that feature frame so repeated
replays can reuse the generated feature parquet when the input contract has not changed.

## Implementation

- Added `feature_cache_dir` to `configs/ct169-older-holdout-replay.json`.
- Added `research.historical-holdout-feature-cache.v1` artifacts:
  - `manifest.json`;
  - `rows.parquet`.
- Cache key includes:
  - dataset manifest path and digest;
  - funding manifest path and digest;
  - feature set version;
  - rolling window;
  - higher timeframes.
- Replay reports now include `feature_cache.status`, `cache_key`, `rows_path`, and `manifest_path`.

The cache is research-only and lives under ignored generated outputs. It does not affect live trading
or runtime order placement.

## Verification

Local unit checks:

```sh
.venv/bin/python -m pytest tests/test_historical_holdout_replay.py
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Results:

- `117 passed`;
- `ruff check .` passed;
- `ruff format --check .` passed.

Real CT-169 replay:

- first replay after CT-170 wrote cache with `feature_cache.status = "miss"`;
- second replay reused the cache with `feature_cache.status = "hit"`;
- metrics stayed unchanged:
  - CT-145 no-TON: `1,255` trades, avg R `0.0287`, max DD `4.34%`;
  - CT-156 high-beta+DOT: `672` trades, avg R `0.0716`, max DD `8.32%`.

Residual bottleneck: cache-hit replay still took about `340s`, because it still reads the 1GB feature
parquet, loads source OHLCV for labels and entry prices, and runs candidate ranking. CT-170 removes
feature regeneration, but a separate streaming/candidate-cache improvement would be needed to make
older-holdout replays fast.
