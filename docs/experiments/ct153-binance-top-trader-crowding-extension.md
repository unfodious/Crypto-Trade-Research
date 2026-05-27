# CT-153 Binance Top-Trader Crowding Extension

Date: 2026-05-27

Issue: CT-153

Epic: CT-113

## Decision

Extended the CT-151 Binance USD-M crowding collector with top-trader account and position
long/short ratios. This remains research-only forward data collection and does not change CT-145
paper-candidate decisions or live trading behavior.

## Motivation

The current CT-113 direction needs external futures context rather than more OHLCV-derived filters.
Top-trader crowding can tell us whether the largest margin-balance cohort is structurally long or
short at the time a signal appears. It is not a trade signal by itself; it is a candidate context
field for later validation.

Official Binance public endpoints checked on 2026-05-27:

- `GET /futures/data/topLongShortPositionRatio`
- `GET /futures/data/topLongShortAccountRatio`

Both endpoints return the most recent data when no `startTime` or `endTime` is supplied and expose
only the latest 30 days, so CT-153 collects them forward with `source_available_at`.

## Implementation

Added two clean parquet tables to each CT-151 snapshot dataset:

- `top_long_short_position_ratio.parquet`
- `top_long_short_account_ratio.parquet`

The manifest now records their paths, hashes, source URLs, period, limit, warnings, and the combined
row count. A healthy CT-153 snapshot for the current 11-symbol universe should contain `55` rows:
`11` symbols times `5` source tables.

## Validation Results

Local one-shot:

| Field | Value |
| --- | ---: |
| latest generated at | `2026-05-27T10:57:20Z` |
| row count | `55` |
| warnings | `0` |

Droplet one-shot on `Paper-trading-test` (`209.38.188.101`):

| Field | Value |
| --- | ---: |
| latest generated at | `2026-05-27T10:58:20Z` |
| generator version | `ct153.binance_crowding_forward.v2` |
| row count | `55` |
| warnings | `0` |
| service result | `success` |
| timer status | `active` |

## Safety Boundary

- Public REST reads only.
- No API credentials.
- No order placement, cancellation, leverage, margin, stop, or take-profit changes.
- No CT-145 strategy behavior change.
- No working-model or live-trading approval.

## Validation Before Use

These fields can influence a later model only after a separate validation issue proves they improve
forward evidence against no-crowding and funding-only baselines with point-in-time joins, enough
sample size, positive OOS avg R after costs, acceptable drawdown, and no single-symbol dominance.
