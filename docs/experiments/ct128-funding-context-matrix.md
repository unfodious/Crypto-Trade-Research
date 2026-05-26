# CT-128 Funding-Rate Crowding Context Matrix

Date: 2026-05-27

Issue: CT-128

Epic: CT-113

## Decision

Rejected for direct promotion, but not discarded. CT-128 is the first CT-113 branch to produce a
credible research candidate that clears the main expectancy, trade-count, and drawdown gates:

- candidate: `ct128_long_negative_funding_expected_r_top3`
- side: long
- thesis: negative funding may identify crowded shorts vulnerable to short-covering continuation
- OOS trades: `101`
- average R after costs: `0.1616`
- max drawdown: `7.20%`
- rule-only average R: `-0.6642`
- top-N nearby rows: top1/top2/top3/top5 all positive with `100-101` trades

This is not a working model yet. It still fails the current promotion record because stability
evidence is not implemented as a passable artifact, the expected-R threshold selected fallback
`0.00` due insufficient validation-threshold exposure, and no paper-trading plan exists. Backtests
remain research evidence only; no paper-trading or live approval is granted.

Next action: create a focused stability-validation issue for the CT-128 long negative-funding
candidate before any paper-trading plan.

## Data Feasibility

Funding-rate history was feasible from Binance USD-M futures public REST data. The official endpoint
used was:

`https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History`

Endpoint characteristics used in CT-128:

- path: `/fapi/v1/fundingRate`
- public endpoint; no API key required
- fields: `symbol`, `fundingRate`, `fundingTime`, `markPrice`
- ascending order by `fundingTime`
- `limit` up to `1000`
- shared documented weight limit: `500/5min/IP`

Generated dataset:

- dataset: `ct128_six_month_funding_rate_dataset`
- rows: `6,516`
- symbols: `ADAUSDT`, `ATOMUSDT`, `AVAXUSDT`, `BTCUSDT`, `DOTUSDT`, `ETHUSDT`,
  `ICPUSDT`, `SOLUSDT`, `SUIUSDT`, `TONUSDT`, `XRPUSDT`
- min funding time: `2025-11-25T00:00:00Z`
- max funding time: `2026-05-24T20:00:00.002000Z`
- warnings: none

## Implementation

Added a research-only funding-rate ingestion module:

- `crypto-trade-ingest-funding-rates`
- `FundingRateDatasetConfig`
- `generate_funding_rate_dataset`
- Parquet raw/clean outputs plus manifest
- duplicate-key and value validation
- deterministic test fetcher support

Added point-in-time funding feature joins:

- `funding_rate`
- `funding_rate_mean_20`
- `funding_rate_zscore_20`
- `funding_rate_abs_zscore_20`
- `funding_rate_positive`
- `funding_rate_abs`
- `hours_since_funding`
- `hours_to_next_funding_estimate`
- `market_average_funding_rate`
- `market_positive_funding_fraction`
- `btc_funding_rate`
- `eth_funding_rate`
- `relative_funding_vs_btc`
- `relative_funding_vs_eth`

The join only uses funding rows where `funding_time` and `source_available_at` are at or before the
decision time.

Added runner and batch support for:

- `funding_manifest_path`
- cached funding rows in batch experiments
- funding manifest path in report metadata

## Data

Candle dataset: `ct121_six_month_core_futures_dataset`

Candle rows: `2,867,040`

Funding dataset: `ct128_six_month_funding_rate_dataset`

Funding rows: `6,516`

Splits:

- train end: `2026-03-25T00:00:00Z`
- validation end: `2026-04-25T00:00:00Z`
- test end: `2026-05-25T00:00:00Z`

## Matrix

Config:

- `configs/ct128-funding-context-base.json`
- `configs/ct128-funding-context-matrix.json`

Batch result: `8/8` completed, `0` failed.

Validation exposure floor: `50` trades.

Predeclared variants:

- short positive-funding crowded-longs expected-R
- short positive-funding crowded-longs probability
- short positive-funding risk-off expected-R
- short positive-funding sell-pressure expected-R
- long negative-funding crowded-shorts expected-R
- long negative-funding crowded-shorts probability
- long negative-funding risk-on expected-R
- long negative-funding buy-pressure expected-R

## Results

| Experiment | Primary | Avg R | Rule Avg R | Trades | Max DD | Decision |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| short positive funding expected-R | expected-R | -0.2519 | -0.6866 | 13 | 0.79% | reject |
| short positive funding probability | probability | -0.0228 | -0.6866 | 1156 | 45.91% | reject |
| short positive funding risk-off expected-R | expected-R | 0.0092 | -0.5169 | 38 | 1.91% | reject |
| short positive funding sell-pressure expected-R | expected-R | -0.4250 | -0.6535 | 12 | 0.71% | reject |
| long negative funding expected-R | expected-R | 0.1616 | -0.6642 | 101 | 7.20% | reject |
| long negative funding probability | probability | 0.1132 | -0.6642 | 2599 | 66.74% | reject |
| long negative funding risk-on expected-R | expected-R | 0.3440 | -0.4738 | 79 | 2.11% | reject |
| long negative funding buy-pressure expected-R | expected-R | 0.0250 | -0.6536 | 75 | 10.18% | reject |

## Candidate Notes

The strongest candidate is `ct128_long_negative_funding_expected_r_top3`.

Primary gates:

- beats rule-only and no-trade: pass
- positive average R: pass
- `>=100` OOS trades: pass (`101`)
- max drawdown `<=8%`: pass (`7.20%`)
- drawdown duration gate: pass (`55` bars)
- leakage status: pass by point-in-time feature construction
- stability artifact: not passed
- paper-trading plan: missing

Top-N sensitivity:

| Strategy | Trades | Avg R | Max DD | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| expected-R top1 | 100 | 0.2050 | 7.20% | 1.3231 |
| expected-R top2 | 100 | 0.1750 | 7.20% | 1.2708 |
| expected-R top3 | 101 | 0.1616 | 7.20% | 1.2481 |
| expected-R top5 | 100 | 0.1150 | 7.20% | 1.1717 |

Positive but not sufficient:

- `ct128_long_negative_funding_riskon_expected_r_top3` had higher avg R (`0.3440`) and low DD
  (`2.11%`) but only `79` trades.
- broad probability exposure had `2599` trades and avg R `0.1132`, but DD was `66.74%`.

## Interpretation

Funding data is materially more useful than another technical-indicator layer. The promising pocket
is long-side negative funding, not short-side positive funding. That is consistent with a crowded
shorts / short-covering interpretation.

However, CT-128 should not be promoted directly. The next branch must validate stability before
paper trading:

- symbol/session/day breadth,
- adjacent funding thresholds,
- horizon sensitivity,
- top-N sensitivity,
- validation exposure weakness from expected-R threshold fallback,
- paper-trading risk plan only if stability survives.

CT-113 remains open.
