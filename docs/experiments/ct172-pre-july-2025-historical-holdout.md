# CT-172 Pre-July 2025 Historical Holdout

Status: rejected; no live approval.

CT-172 extends CT-113 validation with a second older pre-selection holdout. CT-169 showed that the
frozen CT-145 no-TON and CT-156 high-beta plus DOT paper candidates survived July-November 2025.
CT-172 tests whether that evidence holds in an even earlier market window, without retraining,
recalibration, filter changes, symbol re-selection, or live trading changes.

## Data

- OHLCV source: Binance USD-M futures 1m candles imported through the backend historical importer.
- Holdout window: `2025-01-01T00:01:00Z` through `2025-07-01T00:00:00Z`.
- Symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`,
  `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`.
- OHLCV rows: `2,867,040`.
- Funding rows: `6,516`.
- OHLCV manifest: `data/generated/ct172_pre_july_2025_holdout_core_futures_dataset/manifest.json`.
- Funding manifest: `data/generated/ct172_pre_july_2025_holdout_funding_rate_dataset/manifest.json`.

The local backend database initially only contained `2025-07-01` through `2026-05-24`. CT-172
therefore imported `2025-01-01` through `2025-06-30` from Binance public USD-M futures daily kline
archives before exporting into the research dataset contract.

## Method

Replay runner: `python -m crypto_trade_research.historical_holdout_replay`.

Config: `configs/ct172-pre-july-2025-holdout-replay.json`.

Replay rules:

- use frozen pack manifests from CT-145 and CT-156;
- generate the same `features.ct138.regime-symbol-refinement.v1` feature set;
- apply the existing negative-funding/risk-on candidate filters;
- score with the frozen `expected_r_model`;
- keep the frozen expected-R threshold and top-3 per decision time;
- evaluate 12-bar long labels with the same `0.4%` stop, `0.8%` target, stop-first tie breaker,
  and `0.07%` round-trip cost assumption;
- apply the same research risk controls in the backtest layer.

No training, validation threshold selection, symbol re-selection, or filter tuning was performed on
this pre-July 2025 holdout.

## Results

| Candidate | Holdout trades | Avg R | Max DD | Profit factor | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| CT-145 no-TON | 2,242 | -0.0083 | 9.85% | 0.9849 | reject |
| CT-156 high-beta + DOT | 1,096 | -0.0215 | 11.17% | 0.9654 | reject |

CT-145 accepted-trade symbol slices:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| ADAUSDT | 478 | -0.1014 |
| AVAXUSDT | 355 | 0.1354 |
| ICPUSDT | 209 | -0.0079 |
| SOLUSDT | 600 | 0.0139 |
| SUIUSDT | 600 | -0.0415 |

CT-156 accepted-trade symbol slices:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| ADAUSDT | 208 | -0.1603 |
| AVAXUSDT | 116 | 0.3518 |
| DOTUSDT | 142 | 0.1273 |
| ICPUSDT | 47 | -0.0249 |
| SOLUSDT | 317 | -0.0232 |
| SUIUSDT | 266 | -0.1526 |

Session slices were mixed:

| Candidate | Asia Avg R | Europe Avg R | US Avg R |
| --- | ---: | ---: | ---: |
| CT-145 no-TON | -0.0311 | 0.0268 | -0.0228 |
| CT-156 high-beta + DOT | 0.0102 | 0.0544 | -0.1210 |

Artifacts:

- `data/generated/ct172_pre_july_2025_holdout_replay/replay_report.json`;
- `data/generated/ct172_pre_july_2025_holdout_replay/replay_report.md`;
- `data/generated/ct172_pre_july_2025_holdout_replay/ct145_no_ton_negative_funding_paper_pack/accepted_trades.parquet`;
- `data/generated/ct172_pre_july_2025_holdout_replay/ct156_high_beta_dot_shadow_paper_pack/accepted_trades.parquet`.

Cache verification:

- first CT-172 replay generated the feature and pack replay caches;
- second CT-172 replay reported `feature_cache.status=hit` and `replay_cache.status=hit`;
- cached replay preserved the same headline metrics.

## Interpretation

CT-172 rejects the current CT-145 and CT-156 candidates as working-model candidates. CT-169 was
positive on July-November 2025, but the earlier January-June 2025 holdout turned both candidates
negative after costs with larger drawdowns. That means the apparent edge is regime-dependent and not
stable enough for promotion.

Important lessons:

- The candidates still generate plenty of trades, so this is not a sparse-evidence failure.
- AVAX remained positive in both packs, but broad symbol breadth failed.
- The US session was a material drag, especially for CT-156.
- The evidence does not justify loosening filters or approving live trading.

This is still research-only backtest evidence. It does not place, cancel, resize, or close orders,
and it does not approve paper-to-live promotion.

## Next Step

Keep CT-113 open. Keep CT-145 and CT-156 forward streams as observation-only, but do not treat them
as working candidates after CT-172.

Created CT-173 to diagnose the regime failure across Jan-Jun 2025, Jul-Nov 2025, and Nov 2025-May
2026 before proposing another CT-113 candidate. CT-172 should not be used as a direct tuning target
unless a fresh untouched validation slice or forward-data gate is reserved.
