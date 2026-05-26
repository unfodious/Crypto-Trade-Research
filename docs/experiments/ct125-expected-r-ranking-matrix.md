# CT-125 Expected-R Ranking And Calibration Exposure Floor

Date: 2026-05-26

Issue: CT-125

Epic: CT-113

## Decision

Rejected. Expected-R ranking and a validation exposure floor improved calibration hygiene, but did
not produce a paper-trading candidate. The only positive primary row had `34` OOS trades, below the
`>=100` gate. The only row with broad exposure had negative average R and excessive drawdown.

Backtests remain research evidence only. No paper-trading pack is approved.

## Hypothesis

CT-124 showed that validation-selected probability thresholds could overfit tiny validation samples.
CT-125 tested two changes:

- add `min_validation_trades_for_threshold` so a threshold cannot win calibration unless it has
  enough validation exposure,
- add `expected_r_ridge`, a simple ridge regression trained directly on realized R after costs, then
  rank top-N signals by predicted expected R.

This changes the selection objective. It does not change the realized-R backtest, costs, splits, or
promotion gates.

## Implementation

Added research support for:

- `baseline.min_validation_trades_for_threshold`
- `baseline.expected_r_threshold_candidates`
- `baseline.primary_strategy`
- `expected_r_ridge`
- `expected_r_ridge_risk_controlled`
- `expected_r_ridge_topN_oos`
- expected-R validation threshold sweep reporting

The probability threshold sweep now reports whether each threshold meets the exposure floor. If no
threshold meets the floor, the runner falls back to the configured default and records
`fallback_insufficient_validation_trades`.

## Data

Dataset: `ct121_six_month_core_futures_dataset`

Rows: `2,867,040`

Symbols:

`SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`, `TONUSDT`,
`DOTUSDT`, `BTCUSDT`, `ETHUSDT`

Date range:

- min close time: `2025-11-25T00:01:00Z`
- max close time: `2026-05-25T00:00:00Z`

Splits:

- train end: `2026-03-25T00:00:00Z`
- validation end: `2026-04-25T00:00:00Z`
- test end: `2026-05-25T00:00:00Z`

## Matrix

Config:

- `configs/ct125-expected-r-ranking-base.json`
- `configs/ct125-expected-r-ranking-matrix.json`

Batch result: `10/10` completed, `0` failed.

Validation exposure floor: `50` trades.

Predeclared variants:

- probability threshold floor comparator on CT-124 broad short risk-off setup
- expected-R broad short risk-off top1/top2/top3/top5
- expected-R volatility disorderly top1/top3
- expected-R BTC/ETH below-MA + volatility disorderly top3
- expected-R breadth extreme top5
- expected-R long h12 strict top3 comparator from CT-122

## Results

| Experiment | Primary | Avg R | Rule Avg R | Trades | Max DD | E[R] threshold | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| short risk-off probability floor top1 | probability | -0.3965 | -0.5376 | 790 | 83.77% | 0.00 | reject |
| short risk-off expected-R top1 | expected-R | -0.7659 | -0.5376 | 22 | 4.25% | 0.00 | reject |
| short risk-off expected-R top2 | expected-R | -0.4250 | -0.5376 | 28 | 4.09% | 0.00 | reject |
| short risk-off expected-R top3 | expected-R | -0.5321 | -0.5376 | 28 | 4.38% | 0.00 | reject |
| short risk-off expected-R top5 | expected-R | -0.4008 | -0.5376 | 31 | 4.07% | 0.00 | reject |
| volatility disorderly expected-R top1 | expected-R | -0.6950 | -0.4139 | 25 | 1.91% | 0.00 | reject |
| volatility disorderly expected-R top3 | expected-R | -0.0587 | -0.4139 | 43 | 1.38% | 0.00 | reject |
| BTC/ETH below MA + vol disorderly expected-R top3 | expected-R | 0.3250 | -0.3882 | 34 | 0.90% | 0.00 | reject |
| breadth extreme expected-R top5 | expected-R | -0.1750 | -0.5187 | 21 | 2.28% | 0.00 | reject |
| long h12 strict expected-R top3 comparator | expected-R | -0.4453 | -0.5638 | 37 | 4.01% | 0.00 | reject |

Best primary average R:

- `ct125_short_riskoff_expected_r_below_ma_vol_disorderly_top3`
- avg R: `0.3250`
- trades: `34`
- max DD: `0.90%`

It failed the `>=100` OOS trade gate. Its expected-R top5 diagnostic improved to avg R `0.4466`,
but still had only `37` trades.

Only broad-exposure primary row:

- `ct125_short_riskoff_probability_floor_top1`
- avg R: `-0.3965`
- trades: `790`
- max DD: `83.77%`

It failed positive expectancy and drawdown gates.

## Calibration Findings

The exposure floor worked as intended.

For the broad short risk-off probability comparator, CT-124 would have selected `p=0.60` from only
`4` validation trades. CT-125 rejected that threshold because it did not meet the `50`-trade
validation floor, selecting `p=0.55` instead:

- `p=0.55`: validation avg R `-0.4595`, validation trades `348`, meets floor
- `p=0.60`: validation avg R `0.3250`, validation trades `4`, fails floor

The expected-R thresholds were even sparser. For the best positive OOS row:

- `E[R] >= 0.00`: validation avg R `0.6250`, validation trades `15`, fails floor
- `E[R] >= 0.10`: validation avg R `0.3250`, validation trades `6`, fails floor

Because no expected-R threshold met the floor, the runner recorded
`fallback_insufficient_validation_trades` and used threshold `0.00`.

## Interpretation

CT-125 fixes a real calibration weakness: tiny validation pockets no longer silently win threshold
selection. However, the expected-R model did not create a working candidate. The same pattern
remains:

- broad exposure is negative after costs,
- positive pockets are too sparse to trust,
- the current 1m OHLCV-derived feature set is not enough to produce stable six-month OOS edge.

The next hypothesis should change the information set rather than continue tuning selection on the
same 1m features. A predeclared multi-timeframe context test is the cleanest next step: add 5m/15m
derived trend, volatility, and breadth context while preserving the six-month split and the exposure
floor.
