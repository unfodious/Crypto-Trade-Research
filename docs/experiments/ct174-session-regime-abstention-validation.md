# CT-174 Session/Regime Abstention Validation

Status: rejected; no live approval.

CT-173 found a post-hoc diagnostic slice: Europe-session trades were positive across Jan-Jun 2025,
Jul-Nov 2025, and Mar-May 2026 for both CT-145 and CT-156. CT-174 tests that idea as a predeclared
abstention layer on a fresh validation slice, instead of promoting a pattern discovered after the
fact.

## Predeclared Hypothesis

Use the frozen CT-145 and CT-156 packs unchanged, but only allow selected trades with decision times
in the Europe session, defined as `08:00 <= UTC hour < 16:00`.

No model retraining, threshold tuning, symbol re-selection, or live trading change is allowed.

## Fresh Validation Data

- Source: Binance USD-M futures 1m candles imported through the backend historical importer.
- Holdout window: `2024-07-01T00:01:00Z` through `2025-01-01T00:00:00Z`.
- Symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`,
  `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`.
- OHLCV rows: `2,914,560`.
- Funding rows: `6,624`.
- OHLCV manifest: `data/generated/ct174_2024h2_holdout_core_futures_dataset/manifest.json`.
- Funding manifest: `data/generated/ct174_2024h2_holdout_funding_rate_dataset/manifest.json`.

This H2 2024 slice was not used to discover the Europe-session hypothesis.

## Implementation

Added an optional research-only `accepted_sessions` field to the historical holdout replay config.
When present, selected rows outside the accepted sessions are removed before label generation and
before the backtest risk-control layer. This is stricter than filtering already accepted trades after
the backtest, because cooldown and per-symbol/per-time risk controls are applied after abstention.

Configs:

- `configs/ct174-2024h2-holdout-base-replay.json`;
- `configs/ct174-2024h2-holdout-europe-session-replay.json`.

Both configs share the same feature cache:

- `data/generated/ct174_2024h2_holdout_feature_cache`.

## Results

| Candidate | Run | Selected rows | Trades | Avg R | Max DD | Profit factor | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| CT-145 no-TON | base frozen pack | 3,460 | 1,511 | 0.1455 | 3.74% | 1.3029 | diagnostic pass |
| CT-145 no-TON | Europe-only | 1,309 | 612 | 0.0121 | 3.61% | 1.0204 | reject |
| CT-156 high-beta+DOT | base frozen pack | 1,390 | 654 | 0.0286 | 8.21% | 1.0481 | reject: DD |
| CT-156 high-beta+DOT | Europe-only | 671 | 314 | -0.0003 | 7.57% | 0.9995 | reject |

The Europe-only filter did not improve the fresh validation layer. It reduced exposure and removed
some drawdown, but it also removed too much edge. CT-156 remained effectively flat-to-negative, and
CT-145 fell from a healthy H2 2024 base result to a marginal result.

## Fresh Slice Session Evidence

Base CT-145 by session:

| Session | Trades | Avg R |
| --- | ---: | ---: |
| Asia | 439 | 0.2223 |
| Europe | 583 | 0.0513 |
| US | 489 | 0.1890 |

Base CT-156 by session:

| Session | Trades | Avg R |
| --- | ---: | ---: |
| Asia | 172 | 0.3490 |
| Europe | 309 | -0.0238 |
| US | 173 | -0.1963 |

The fresh H2 2024 data directly contradicts the CT-173 post-hoc Europe-only idea. Europe was not the
dominant source of edge in CT-145 and was negative for CT-156.

## Interpretation

CT-174 rejects the Europe-session abstention hypothesis. The CT-173 Europe pattern was a diagnostic
artifact, not a robust promotion rule.

The base frozen CT-145 result on H2 2024 is useful evidence: CT-145 is positive on H2 2024,
Jul-Nov 2025, and Mar-May 2026, but still fails Jan-Jun 2025. That points back to a specific
deleveraging or persistent weakness regime rather than a simple session rule.

This does not restore CT-145 as a working model because CT-172 remains a high-trade-count rejection.
Any next candidate must explain or abstain from the Jan-Jun 2025 failure without simply fitting that
period.

## Decision

No working model claim.

No paper-to-live promotion.

Keep CT-113 open.

Keep CT-145 and CT-156 forward-paper streams observation-only.

## Next Step

Created CT-175 to test a predeclared ETH-led deleveraging abstention hypothesis. It must use a
strict walk-forward design or reserve an untouched validation slice; it must not tune directly
against CT-172 until it passes.
