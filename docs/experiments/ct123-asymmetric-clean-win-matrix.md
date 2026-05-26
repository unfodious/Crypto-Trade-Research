# CT-123 Asymmetric Clean-Win Objective Matrix

Date: 2026-05-26

Issue: CT-123

Epic: CT-113

## Decision

Rejected. The asymmetric clean-win training objective did not produce a paper-trading candidate on
the six-month full-universe dataset. It reduced trade count and sometimes reduced drawdown, but
average R stayed negative after costs across every row.

Backtests remain research evidence only. No paper-trading pack is approved.

## Hypothesis

CT-122 showed that the h12 long breakout pocket had enough trades on six months, but negative
expectancy and excessive drawdown. CT-123 tested whether the issue was the supervised target: instead
of training the multifeature ridge model to predict only `target_before_stop`, train it to prefer
"clean wins" where target is reached and max adverse excursion is bounded.

This is an abstention objective. It changes model selection, not the realized-R backtest. All
strategy reports still evaluate the same h12 long 2R/1R label assumptions after costs.

## Implementation

Added `training_target` support:

- `target_before_stop`: default behavior.
- `positive_r_after_costs`: positive target when realized R is non-negative.
- `clean_win_max_adverse_r`: positive target when target is reached, realized R is non-negative, and
  `max_adverse_excursion_r` stays above a configured floor.

The chosen target is recorded in baseline metadata, model artifact preprocessing metadata, and
experiment registry metrics.

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

## Matrix

Config:

- `configs/ct123-asymmetric-clean-win-base.json`
- `configs/ct123-asymmetric-clean-win-matrix.json`

Predeclared variants:

- clean-win MAE floors: `-0.25R`, `-0.50R`, `-0.75R`
- top1/top3/top5 ranking for the `-0.50R` target
- positive-R target comparator
- BTC/ETH above-MA slice
- volatility normal and disorderly slices
- BTC/ETH above-MA + volatility disorderly slice

Batch result: `10/10` completed, `0` failed.

## Results

| Experiment | Avg R | Rule Avg R | Trades | Max DD | Selected p | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| clean MAE `-0.50R` top1 | -0.4092 | -0.5638 | 427 | 62.73% | 0.55 | reject |
| clean MAE `-0.25R` top1 | -0.2574 | -0.5638 | 85 | 11.59% | 0.55 | reject |
| clean MAE `-0.75R` top1 | -0.4195 | -0.5638 | 683 | 80.10% | 0.55 | reject |
| clean MAE `-0.50R` top3 | -0.2874 | -0.5638 | 703 | 70.32% | 0.55 | reject |
| clean MAE `-0.50R` top5 | -0.3291 | -0.5638 | 798 | 78.82% | 0.55 | reject |
| positive R top1 | -0.3298 | -0.5638 | 969 | 84.45% | 0.55 | reject |
| clean MAE `-0.50R`, BTC/ETH above MA top1 | -0.3993 | -0.5301 | 437 | 64.15% | 0.55 | reject |
| clean MAE `-0.50R`, volatility normal top1 | -0.5839 | -0.6388 | 741 | 90.49% | 0.50 | reject |
| clean MAE `-0.50R`, volatility disorderly top1 | -0.3313 | -0.3524 | 224 | 35.32% | 0.50 | reject |
| clean MAE `-0.50R`, BTC/ETH above MA + vol disorderly top1 | -0.3179 | -0.3311 | 105 | 21.31% | 0.55 | reject |

Best average R was the strict `-0.25R` clean-win top1 row:

- avg R: `-0.2574`
- trades: `85`
- max drawdown: `11.59%`

It failed positive expectancy, minimum trade count, drawdown, stability, and paper-plan gates.

Best row with `>=100` OOS trades by drawdown was the BTC/ETH above-MA + volatility disorderly row:

- avg R: `-0.3179`
- trades: `105`
- max drawdown: `21.31%`

It still failed positive expectancy and drawdown gates.

## Interpretation

The asymmetric objective helped reduce exposure in some variants, but it did not recover the h12 long
breakout family. The result strengthens the CT-122 conclusion: the issue is not just probability
thresholding, top-N selection, or supervised target definition. This long breakout setup family is
not currently a working candidate on the six-month evidence.

The next hypothesis should move away from this long h12 setup family. A short-side risk-off
continuation setup is a cleaner next test because it changes the market behavior being modeled
rather than continuing to filter a rejected long breakout pocket.
