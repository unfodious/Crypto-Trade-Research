# CT-124 Short Risk-Off Continuation Matrix

Date: 2026-05-26

Issue: CT-124

Epic: CT-113

## Decision

Rejected. The six-month short-side risk-off continuation matrix did not produce a paper-trading
candidate. Every primary matrix row had negative model OOS average R after costs. Some top-N
diagnostic rows turned positive, but only with `12` to `23` OOS trades, far below the `>=100` gate.

Backtests remain research evidence only. No paper-trading pack is approved.

## Hypothesis

CT-122 and CT-123 rejected the h12 long breakout family after probability calibration, top-N
ranking, regime slicing, and asymmetric clean-win targets. CT-124 changed the setup family rather
than tuning the same long pocket:

If the market is in a risk-off state, a short continuation setup near the candle/range low may have
better continuation expectancy than the rejected long breakout family.

The setup was predeclared with:

- short h12 label, 2R target, 1R stop, costs included
- `volatility_expansion_20 >= 1.3`
- `close_location <= 0.3`
- risk-off breadth/reference context using `risk_on_score_20` and
  `market_positive_return_fraction`
- BTC/ETH shock and trend slices
- volatility expanded/disorderly slices
- validation-selected probability threshold
- explicit same-timestamp top1/top2/top3/top5 ranking

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

The runner used `memory.label_generation_mode = candidate_only`, so labels were generated only for
rows matching each predeclared candidate setup.

## Matrix

Config:

- `configs/ct124-short-riskoff-continuation-base.json`
- `configs/ct124-short-riskoff-continuation-matrix.json`

Batch result: `10/10` completed, `0` failed.

Predeclared variants:

- base short risk-off continuation top1/top2/top3/top5
- BTC/ETH both below MA top1
- BTC/ETH negative one-bar shock top1
- extreme breadth/risk-off top1
- volatility expanded top1
- volatility disorderly top1
- BTC/ETH both below MA + volatility disorderly top1

## Results

| Experiment | Avg R | Rule Avg R | Trades | Max DD | Selected p | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| base top1 | -0.4250 | -0.5376 | 16 | 6.34% | 0.60 | reject |
| base top2 | -0.2276 | -0.5376 | 19 | 5.29% | 0.60 | reject |
| base top3 | -0.2750 | -0.5376 | 20 | 5.60% | 0.60 | reject |
| base top5 | -0.2205 | -0.5376 | 22 | 5.70% | 0.60 | reject |
| BTC/ETH below MA top1 | -0.3568 | -0.5265 | 11 | 4.64% | 0.60 | reject |
| BTC/ETH negative shock top1 | -0.4827 | -0.5024 | 13 | 5.33% | 0.60 | reject |
| breadth extreme top1 | -0.2750 | -0.5187 | 10 | 4.31% | 0.60 | reject |
| volatility expanded top1 | -0.1750 | -0.5722 | 12 | 3.27% | 0.60 | reject |
| volatility disorderly top1 | -0.4856 | -0.4139 | 161 | 38.97% | 0.55 | reject |
| BTC/ETH below MA + vol disorderly top1 | -0.1750 | -0.3882 | 15 | 4.24% | 0.60 | reject |

Best primary average R:

- `ct124_short_riskoff_vol_expanded_top1`
- avg R: `-0.1750`
- trades: `12`
- max DD: `3.27%`

Only primary row with `>=100` OOS trades:

- `ct124_short_riskoff_vol_disorderly_top1`
- avg R: `-0.4856`
- trades: `161`
- max DD: `38.97%`

It failed positive expectancy, rule-only comparison, drawdown, stability, and paper-plan gates.

## Ranking Diagnostics

Several top-N diagnostics were positive but too sparse:

| Experiment | Diagnostic | Avg R | Trades | Max DD |
| --- | --- | ---: | ---: | ---: |
| breadth extreme | top3 | 0.0750 | 12 | 3.91% |
| breadth extreme | top5 | 0.3250 | 14 | 3.91% |
| BTC/ETH negative shock | top5 | 0.1583 | 18 | 5.33% |
| BTC/ETH below MA + vol disorderly | top3 | 0.1293 | 23 | 3.49% |
| BTC/ETH below MA + vol disorderly | top5 | 0.1293 | 23 | 3.49% |

These are not candidates because they are below the `>=100` OOS trade gate. They are better treated
as a calibration warning: validation threshold selection can overfit to tiny validation samples and
then produce sparse OOS exposure.

## Regime Notes

The broad base setup produced `156,718` candidate label rows and `32,431` trainable samples, so the
rejection is not caused by insufficient candidate coverage.

Rule-only short risk-off was consistently negative:

- base rule-only OOS avg R: `-0.5376` over `7,361` trades
- BTC/ETH below-MA rule-only OOS avg R: `-0.5265` over `6,352` trades
- volatility disorderly rule-only OOS avg R: `-0.4139` over `1,080` trades

The classifier selected `p=0.60` for most rows because the validation sweep preferred tiny samples:

- base `p=0.60`: validation avg R `0.3250` on only `4` trades
- breadth extreme `p=0.60`: validation avg R `1.8250` on only `2` trades
- BTC/ETH below MA + volatility disorderly `p=0.60`: validation avg R `-0.1750` on only `6` trades

The one row with broader selected exposure, volatility disorderly top1, selected `p=0.55`, had
`161` OOS trades, but avg R was `-0.4856` and max DD was `38.97%`.

## Interpretation

CT-124 changes the setup family and confirms that the current multifeature probability classifier
does not recover a working six-month candidate by switching from long breakout to short risk-off
continuation.

Two separate issues appeared:

- broad short risk-off continuation is negative after costs,
- validation-selected probability thresholds can choose tiny validation samples, creating positive
  but unusably sparse diagnostics.

The next hypothesis should not loosen these filters. A better next step is an expected-R ranking or
calibration robustness layer that directly ranks realized-R expectancy and enforces a minimum
validation exposure floor before a threshold can be selected.
