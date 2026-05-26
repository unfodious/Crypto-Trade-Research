# CT-129 Dynamic Breakeven And Trailing Exit Matrix

Date: 2026-05-27

Issue: CT-129

Epic: CT-113

## Decision

Rejected. CT-129 tested a research-only dynamic exit model after repeated fixed 2R/1R rejects. The
idea is valid strategy research: keep a predefined 1R initial stop, move the stop to breakeven or a
small positive lock after a favorable 1R move, optionally trail by an R distance, and exit at the
horizon if no stop is hit. This changes the label/backtest exit model, not live order placement.

The dynamic exit improved some raw rule-only losses versus fixed 2R, but it did not create a
tradeable candidate. Broad probability-ranked exposure stayed negative with extreme drawdown.
Expected-R ranking became too sparse, usually producing 1 to 7 OOS trades. The only positive primary
row had 4 OOS trades, far below the `>=100` gate.

Backtests remain research evidence only. No paper-trading pack is approved.

## Why This Was Tested

Adding more nearby OHLCV indicators or another simple timeframe layer was deprioritized because
CT-121 through CT-127 already tested rich OHLCV, regime, MTF, expected-R ranking, and kline
taker-flow context. More of the same would likely increase overfit risk.

Dynamic stop management is more defensible because exits, stop behavior, and position lifecycle are
first-class parts of a strategy. The test was predeclared and conservative: same-bar ambiguity uses
`stop_first`.

## Implementation

Added label support for:

- `exit_model`: `fixed_target_stop` or `breakeven_trailing`
- `breakeven_activation_r`
- `breakeven_lock_r`
- `trailing_stop_r`
- `time_to_breakeven_bars`
- `dynamic_exit_reason`

The dynamic model:

- starts with the configured 1R stop,
- checks the current stop first on each future bar,
- moves the stop after favorable movement reaches the configured activation R,
- optionally trails by a configured R distance from the favorable high/low,
- exits by dynamic stop or horizon close,
- subtracts costs in R units.

Added unit coverage for long, short, breakeven activation, trailing stop, horizon exit, and same-bar
stop-after-activation ambiguity.

Added compact experiment reporting for large matrices. CT-129 keeps metrics, gates, thresholds,
regime slices, and counts, but omits raw `trades` and `equity_curve` arrays from JSON reports to
avoid multi-hundred-MB artifacts.

## Data

Dataset: `ct121_six_month_core_futures_dataset`

Rows: `2,867,040`

Symbols:

`SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`, `TONUSDT`,
`DOTUSDT`, `BTCUSDT`, `ETHUSDT`

Splits:

- train end: `2026-03-25T00:00:00Z`
- validation end: `2026-04-25T00:00:00Z`
- test end: `2026-05-25T00:00:00Z`

Feature context reused the CT-127 six-month kline microstructure plus 5m/15m MTF feature set.

## Matrix

Config:

- `configs/ct129-dynamic-exit-base.json`
- `configs/ct129-dynamic-exit-matrix.json`

Batch result: `9/9` completed, `0` failed.

Validation exposure floor: `50` trades.

Predeclared variants:

- fixed short sell-pressure 24-bar comparator
- short sell-pressure breakeven-only
- short sell-pressure breakeven plus 1.0R trailing
- short sell-pressure breakeven plus 1.5R trailing, top3/top5
- short sell-pressure risk-off plus 1.5R trailing
- long buy-pressure probability-ranked plus 1.5R trailing
- long buy-pressure expected-R-ranked plus 1.5R trailing
- long buy-pressure risk-on plus 1.5R trailing

## Results

| Experiment | Primary | Avg R | Rule Avg R | Trades | Max DD | Decision |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| fixed short sell-pressure comparator | expected-R | -0.3136 | -0.5695 | 101 | 8.68% | reject |
| short sell-pressure breakeven-only | expected-R | -0.2191 | -0.2243 | 7 | 0.03% | reject |
| short sell-pressure trailing 1.5R | expected-R | -0.3026 | -0.2294 | 5 | 0.02% | reject |
| short sell-pressure trailing 1.0R | expected-R | -0.4474 | -0.2311 | 1 | 0.00% | reject |
| short sell-pressure trailing 1.5R top5 cap | expected-R | -0.3026 | -0.2294 | 5 | 0.02% | reject |
| short sell-pressure risk-off trailing 1.5R | expected-R | -0.2923 | -0.2339 | 7 | 0.04% | reject |
| long buy-pressure trailing 1.5R probability | probability | -0.0835 | -0.2291 | 6600 | 96.56% | reject |
| long buy-pressure trailing 1.5R expected-R | expected-R | -0.9209 | -0.2291 | 3 | 0.19% | reject |
| long buy-pressure risk-on trailing 1.5R | expected-R | 0.1301 | -0.2316 | 4 | 0.08% | reject |

Primary failure pattern:

- probability-ranked dynamic exposure reaches trade count but remains negative and drawdown-heavy,
- expected-R-ranked dynamic exposure avoids drawdown by barely trading,
- positive sparse rows are far below the `>=100` OOS trade-count gate.

## Label Diagnostics

Dynamic labels were not trivially impossible, but positive outcomes were not dominant:

| Variant | Candidate labels | Positive label fraction | Dynamic stops | Horizon exits |
| --- | ---: | ---: | ---: | ---: |
| short breakeven-only | 284,123 | 31.51% | 98,451 | 185,672 |
| short trailing 1.5R | 284,123 | 33.36% | 105,371 | 178,752 |
| long trailing 1.5R | 274,150 | 32.13% | 102,751 | 171,399 |
| long risk-on trailing 1.5R | 122,069 | 29.81% | 47,934 | 74,135 |

The issue is not that dynamic exits never produce positive labels. The issue is that the current
feature/ranking stack does not select them with enough OOS expectancy and frequency after costs.

## Calibration And Ranking Findings

The probability threshold selected `p=0.55` or `p=0.50` depending on row. Expected-R thresholds
selected `0.00`. Top-N diagnostics did not reveal a robust pocket:

- short dynamic expected-R top1/top2/top3/top5 all selected only 1 to 7 trades and stayed negative,
- long probability top1/top2/top3/top5 all produced thousands of trades, negative average R, and
  `85%` to `99%` drawdown,
- long risk-on expected-R top2/top3/top5 was positive at `0.1301` average R, but only 4 trades.

This is not enough evidence for paper trading.

## Interpretation

Dynamic breakeven/trailing exits are a reasonable idea, but CT-129 rejects them under the current
signal stack. They reduce some fixed-target damage, yet they do not solve selection. The model still
cannot reliably identify which candidate bars deserve capital.

CT-113 should remain open. The next useful branch is not another minor indicator stack. The next
branch should add genuinely different information, with CT-128 funding-rate history as the current
best candidate.
