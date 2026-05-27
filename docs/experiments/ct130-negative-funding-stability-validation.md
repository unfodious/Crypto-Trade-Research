# CT-130 Negative-Funding Long Candidate Stability Validation

Date: 2026-05-27

Issue: CT-130

Epic: CT-113

## Decision

Prepared as a paper-trading candidate, not a working model and not live-trading approved.

The CT-128 long negative-funding pocket survived CT-130 stability validation better than prior
CT-113 branches. The base candidate passed the explicit stability artifact:

- candidate: `ct130_long_negative_funding_h12_base_top3`
- side: long
- thesis: negative funding may identify crowded shorts vulnerable to short-covering continuation
- primary strategy: `expected_r_ridge_risk_controlled_oos`
- comparable top-N strategy: `expected_r_ridge_top3_oos`
- OOS trades: `238`
- average R after costs: `0.2620`
- rule-only average R: `-0.6642`
- max drawdown: `7.20%`
- validation-selected expected-R threshold: `-0.20`
- stability artifact status: `pass`

This is still only research evidence. The candidate can move to a paper-trading/dry-run issue, but
CT-113 must stay open until paper evidence exists. No live trading approval is granted.

## Data

Candle dataset: `ct121_six_month_core_futures_dataset`

Funding dataset: `ct128_six_month_funding_rate_dataset`

Symbols:

- `SOLUSDT`
- `SUIUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `ICPUSDT`
- `ATOMUSDT`
- `XRPUSDT`
- `TONUSDT`
- `DOTUSDT`
- `BTCUSDT`
- `ETHUSDT`

Splits:

- train end: `2026-03-25T00:00:00Z`
- validation end: `2026-04-25T00:00:00Z`
- test end: `2026-05-25T00:00:00Z`

All funding features are point-in-time joins using funding rows where `funding_time` and
`source_available_at` are at or before the decision time.

## Implementation

Added reproducible stability artifact support:

- `crypto_trade_research.evaluation.stability.evaluate_candidate_stability_from_files`
- `crypto_trade_research.evaluation.stability.segment_breakdown_from_strategy_report`
- CLI module entrypoint via `python -m crypto_trade_research.evaluation.stability`
- console script metadata: `crypto-trade-write-stability-report`

Also changed batch input caching so candidate-only label frames are not retained for every matrix
row. This fixed a Docker `exit 137` failure caused by accumulating large one-off candidate labels
during CT-130. The batch still caches the expensive source rows and feature frame.

## Matrix

Config:

- `configs/ct130-negative-funding-stability-base.json`
- `configs/ct130-negative-funding-stability-matrix.json`

Batch result: `14/14` completed, `0` failed.

Leaderboard:

- `data/generated/ct130_negative_funding_stability_matrix/leaderboard.json`
- `data/generated/ct130_negative_funding_stability_matrix/leaderboard.md`

Stability artifact:

- `data/generated/ct130_negative_funding_stability_matrix/stability_report.json`

Predeclared variants:

- adjacent funding thresholds;
- adjacent funding z-score thresholds;
- close-location sensitivity;
- horizons `12`, `18`, and `24`;
- tight/wide stop sensitivity;
- `1.5R` target sensitivity;
- risk-on and risk-off slices;
- top `1`, `2`, `3`, and `5` ranking inside each run.

## Results

| Experiment | Avg R | Rule Avg R | Trades | Max DD | Selected E[R] | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| h12 base | 0.2620 | -0.6642 | 238 | 7.20% | -0.20 | paper candidate |
| h12 loose funding | 0.2705 | -0.6797 | 303 | 7.02% | -0.20 | supports |
| h12 strict funding | 0.2804 | -0.6559 | 202 | 6.98% | -0.20 | supports |
| h12 loose z-score | 0.1960 | -0.6804 | 221 | 6.85% | -0.20 | supports |
| h12 strict z-score | 0.2168 | -0.6715 | 194 | 7.40% | -0.20 | supports |
| h12 close >= 0.40 | 0.2346 | -0.6610 | 166 | 6.48% | -0.10 | supports |
| h12 close >= 0.50 | 0.1434 | -0.6617 | 223 | 13.09% | -0.20 | DD reject |
| h18 base | 0.2816 | -0.6337 | 346 | 8.27% | -0.20 | DD reject |
| h24 base | 0.3602 | -0.6080 | 256 | 8.58% | -0.10 | DD reject |
| h12 tight stop 2R | -0.0167 | -0.6737 | 217 | 12.44% | -0.20 | reject |
| h12 wide stop 2R | 0.1650 | -0.6377 | 200 | 8.61% | -0.20 | DD reject |
| h12 target 1.5R | 0.1267 | -0.4579 | 121 | 5.84% | 0.00 | supports, lower edge |
| h12 risk-on | 0.3440 | -0.4738 | 79 | 2.11% | 0.00 | sparse |
| h12 risk-off | -0.0541 | -0.8209 | 91 | 16.36% | 0.20 | reject |

Top-N sensitivity for the base candidate:

| Strategy | Trades | Avg R | Max DD | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| expected-R top1 | 218 | 0.2149 | 7.20% | 1.3408 |
| expected-R top2 | 231 | 0.2276 | 7.20% | 1.3638 |
| expected-R top3 | 238 | 0.2620 | 7.20% | 1.4279 |
| expected-R top5 | 239 | 0.2183 | 7.20% | 1.3469 |

Probability top-N had thousands of trades and positive average R, but drawdown stayed unusably high
at roughly `62-70%`. CT-130 therefore keeps the candidate on expected-R ranking, not broad
probability exposure.

## Stability Artifact

`ct130_long_negative_funding_h12_base_top3` passed all explicit stability gates:

| Gate | Result |
| --- | --- |
| positive OOS expectancy | pass |
| beats rule-only OOS | pass |
| minimum trade count | pass (`238 >= 100`) |
| drawdown within limit | pass (`7.20% <= 8.00%`) |
| symbol breadth | pass (`63.64%` positive symbols) |
| session breadth | pass (`100.00%` positive sessions) |
| lucky-day concentration | pass (top positive day share `34.46%`) |
| nearby sensitivity | pass (`85.71%` positive variants) |

Symbol breadth:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| TONUSDT | 93 | 0.3089 |
| ICPUSDT | 76 | 0.2461 |
| DOTUSDT | 26 | 0.5558 |
| SUIUSDT | 9 | 0.4917 |
| ADAUSDT | 8 | 0.3250 |
| SOLUSDT | 9 | 0.1583 |
| AVAXUSDT | 5 | 0.0250 |
| ETHUSDT | 7 | -0.3179 |
| ATOMUSDT | 1 | -1.1750 |
| BTCUSDT | 2 | -1.1750 |
| XRPUSDT | 2 | -1.1750 |

Session breadth:

| Session | Trades | Avg R |
| --- | ---: | ---: |
| Asia | 69 | 0.0859 |
| Europe | 87 | 0.2733 |
| US | 82 | 0.3982 |

## Interpretation

The candidate is materially stronger than the earlier CT-128 result because the expected-R
calibration grid now has enough validation exposure at `-0.20`. However, the negative selected
threshold means the expected-R model should be treated as a ranking model, not as a well-calibrated
absolute expectancy estimator.

What looks robust:

- adjacent funding thresholds stayed positive;
- adjacent z-score thresholds stayed positive;
- top1/top2/top3/top5 all stayed positive;
- h18/h24 stayed positive;
- all sessions were positive;
- the result was not a single lucky day.

What still worries us:

- BTC, ETH, XRP, and ATOM slices are negative or too sparse;
- much of the edge comes from TON, ICP, and DOT;
- risk-off slice is negative with high drawdown;
- h18/h24 are positive but breach the `8%` drawdown gate;
- tight stop fails, so the edge is not invariant to stop placement;
- probability exposure still has unacceptable drawdown.

The most likely current thesis is not generic long alpha. It is a long crowded-short/funding squeeze
candidate that works best outside risk-off conditions.

## Paper-Trading Plan

Paper only. Do not place live orders and do not wire this into runtime order placement.

Candidate:

- `ct130_long_negative_funding_h12_base_top3`

Entry universe:

- same 11 USD-M futures symbols used in CT-130.

Signal:

- long only;
- closed `1m` candles only;
- funding rows must be source-available before decision time;
- filters:
  - `funding_rate <= -0.00002`;
  - `funding_rate_zscore_20 <= -0.25`;
  - `close_location >= 0.45`;
- rank candidates by expected-R ridge score;
- take top `3` candidates per decision time;
- apply `loss_cooldown_signals = 2`;
- keep max decision-time exposure equivalent to the backtest top3 rule.

Exit model:

- stop: `0.4%`;
- target: `0.8%`;
- horizon timeout: `12` bars;
- cost assumption: `7 bps` round-trip equivalent from CT-130 labels.

Paper validation gate:

- minimum `30` calendar days and at least `100` paper trades;
- average R after estimated costs remains positive;
- max simulated drawdown remains `<= 8%`;
- no single day contributes more than `75%` of positive R;
- at least `50%` positive symbol breadth among symbols with trades;
- all major sessions are not persistently negative;
- paper fills, source timestamps, and generated signals reconcile with the research rules.

Kill or pause conditions:

- average R is negative after `50` paper trades;
- simulated drawdown exceeds `8%`;
- risk-off slice dominates losses;
- funding data is missing, delayed, or not source-timestamped;
- live/paper signal generation diverges from the research artifact.

Required next issue:

- implement and run a dry-run/paper-trading candidate pack for this strategy;
- include fake executor or paper ledger only;
- add monitoring for per-symbol, session, drawdown, and data-latency drift;
- no live trading approval.

## Conclusion

CT-130 passes stability validation and produces the first CT-113 paper-trading candidate plan.
Because no paper evidence exists yet, the model is not a working model. CT-113 remains open.
