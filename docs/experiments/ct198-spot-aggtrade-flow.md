# CT-198 Targeted Spot AggTrade Flow

Status: rejected for paper trading; CT-113 should be re-scoped before more spot drawdown filters.

## Thesis

CT-198 tested whether raw Binance Spot `aggTrades` around candidate entry times can identify better
drawdown-breakout entries than OHLCV and kline-level taker-flow.

Economic idea: if a post-drawdown breakout is supported by large aggressive buyer prints shortly
before the entry, it might represent real demand returning rather than a weak bounce.

## Feasibility

Full monthly `aggTrades` ingestion remains too heavy for broad sweeps. Daily archives are practical:

- CT-198 used only the daily `aggTrades` archives for symbol/date pairs where a candidate entry
  occurred.
- Cache size for this diagnostic: `701 MB`.
- Cached daily source files: `68`.

This is feasible for targeted diagnostics, but still too heavy to treat as a casual threshold sweep.

## Implementation

Added `crypto_trade_research.spot_aggtrade_flow`, a research-only diagnostic that:

- extracts portfolio candidate entries from a spot drawdown replay config;
- downloads Binance Spot daily `aggTrades` archives only for the needed symbol/date pairs;
- parses headerless Data Vision CSV rows;
- computes pre-entry metrics over a 30-minute lookback window:
  - aggressive buy notional ratio;
  - buy/sell notional imbalance;
  - 95th-percentile large trade threshold;
  - large aggressive-buy notional ratio;
  - max trade notional.

Artifacts:

- `configs/ct198-spot-aggtrade-flow-30m-5sym.json`
- `configs/ct198-spot-aggtrade-flow-broad-30m.json`
- `data/generated/ct198_spot_aggtrade_flow_30m_5sym/report.json`
- `data/generated/ct198_spot_aggtrade_flow_broad_30m/report.json`

## Selected Five-Symbol Diagnostic

Source scenarios:

- `portfolio_dd6_breakout6_sized125_guard_1000`
- `portfolio_dd6_breakout6_sized150_guard_1000`
- `portfolio_dd6_breakout6_target5_sized125_guard_1000`

Candidate entries: `75`.

Source days: `25`.

| Scenario | Candidates | Avg trade return | Positive rate | Avg buy ratio | Avg imbalance | Avg large-buy ratio | Best viable slice |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd6_breakout6_sized125_guard_1000` | `25` | `6.43%` | `100.00%` | `55.50%` | `11.00%` | `58.30%` | `buy_ratio_55`: `15` trades, `5.70%` |
| `portfolio_dd6_breakout6_sized150_guard_1000` | `25` | `6.43%` | `100.00%` | `55.50%` | `11.00%` | `58.30%` | `buy_ratio_55`: `15` trades, `5.70%` |
| `portfolio_dd6_breakout6_target5_sized125_guard_1000` | `25` | `7.17%` | `100.00%` | `55.50%` | `11.00%` | `58.30%` | `buy_ratio_55`: `15` trades, `6.59%` |

Selected conclusion: every baseline candidate trade is already positive, and the aggressive-buy
slices reduce average trade return and trade count. Raw aggTrade pressure does not improve this
selected pocket.

## Broad Seventeen-Symbol Diagnostic

Source scenarios:

- `portfolio_dd6_broad_breakout6_sized125_guard_1000`
- `portfolio_dd6_broad_breakout6_sized150_guard_1000`
- `ct196_broad_momentum_rank30_open4_failed12_stale72_sized125_1000`

Candidate entries: `115`.

Source days: `50`.

| Scenario | Candidates | Avg trade return | Positive rate | Avg buy ratio | Avg imbalance | Avg large-buy ratio | Best viable slice |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ct196_broad_momentum_rank30_open4_failed12_stale72_sized125_1000` | `31` | `3.38%` | `100.00%` | `55.10%` | `10.20%` | `57.10%` | `large_buy_ratio_60`: `12` trades, `2.70%` |
| `portfolio_dd6_broad_breakout6_sized125_guard_1000` | `42` | `4.77%` | `95.20%` | `54.80%` | `9.50%` | `56.90%` | `buy_ratio_55`: `20` trades, `3.45%` |
| `portfolio_dd6_broad_breakout6_sized150_guard_1000` | `42` | `4.77%` | `95.20%` | `54.80%` | `9.50%` | `56.90%` | `buy_ratio_55`: `20` trades, `3.45%` |

Broad conclusion: raw aggressive-buy slices again underperform the unsliced candidate set. They do
not recover the open-inventory/high-return rows and do not improve the CT-196 no-open risk-control
row.

## Decision

Do not approve live trading.

Do not prepare a paper-trading pack.

Do not claim a working model.

CT-198 rejects the targeted raw-aggTrades confirmation idea for the current spot
drawdown-breakout family. Combined with CT-195, CT-196, and CT-197, the evidence says this family is
not close enough to the user's desired monthly return profile.

CT-113 should now be paused or re-scoped before adding more price/flow filters to the same thesis.
