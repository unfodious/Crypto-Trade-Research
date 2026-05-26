# CT-126 Six-Month Multi-Timeframe Context Matrix

Date: 2026-05-26

Issue: CT-126

Epic: CT-113

## Decision

Rejected. The six-month 5m/15m multi-timeframe context matrix completed cleanly, but no candidate
met the paper-trading gates. Expected-R ranking again found positive pockets, but they remained far
below the `>=100` OOS trade-count gate. Broad probability-ranked exposure produced hundreds of
trades but stayed negative after costs with excessive drawdown.

Backtests remain research evidence only. No paper-trading pack is approved.

## Hypothesis

CT-125 showed that calibration hygiene and expected-R ranking can avoid some bad broad exposure, but
the positive pockets were too sparse. CT-126 tested whether changing the information set with
point-in-time 5m/15m context would make the ranked pockets more stable without loosening filters.

The predeclared context features were derived only from already closed 1m candles:

- 5m/15m return, trend-above-MA, MA slope sign, range position, and volatility bucket
- 5m/15m market positive-return fraction and risk-on score
- 5m/15m BTC and ETH return, trend, and volatility bucket

## Implementation

Added research support for `feature.higher_timeframes` in baseline and batch configs.

The feature generator now derives minute-based higher-timeframe candles from the same OHLCV source
and aligns them by `decision_time <= base decision_time`, so a 1m row only sees the latest fully
closed 5m/15m aggregate. Batch feature caching now includes `higher_timeframes` in its cache key.

Added unit coverage for closed-candle alignment using a 2m derived timeframe.

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

- `configs/ct126-multitimeframe-context-base.json`
- `configs/ct126-multitimeframe-context-matrix.json`

Batch result: `8/8` completed, `0` failed.

Validation exposure floor: `50` trades.

Predeclared variants:

- short MTF risk-off probability comparator
- short MTF risk-off expected-R top1/top3/top5
- short BTC/ETH below-MA expected-R top3
- short volatility-disorderly expected-R top3
- long MTF risk-on breakout probability comparator
- long MTF risk-on breakout expected-R top3

## Results

| Experiment | Primary | Avg R | Rule Avg R | Trades | Max DD | Selected p | E[R] threshold | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| short MTF risk-off probability top1 | probability | -0.3314 | -0.4148 | 889 | 81.04% | 0.50 | 0.00 | reject |
| short MTF risk-off expected-R top1 | expected-R | 0.4132 | -0.4148 | 17 | 0.77% | 0.50 | 0.00 | reject |
| short MTF risk-off expected-R top3 | expected-R | 0.4321 | -0.4148 | 28 | 0.74% | 0.50 | 0.00 | reject |
| short MTF risk-off expected-R top5 | expected-R | 0.3250 | -0.4148 | 30 | 0.84% | 0.50 | 0.00 | reject |
| short BTC/ETH below-MA expected-R top3 | expected-R | 0.2000 | -0.3675 | 24 | 0.96% | 0.55 | 0.00 | reject |
| short volatility-disorderly expected-R top3 | expected-R | -0.6224 | -0.3050 | 38 | 4.78% | 0.50 | 0.00 | reject |
| long MTF breakout probability top3 | probability | -0.1934 | -0.4072 | 871 | 68.15% | 0.55 | 0.00 | reject |
| long MTF breakout expected-R top3 | expected-R | -0.2150 | -0.4072 | 75 | 3.20% | 0.55 | 0.00 | reject |

Best primary average R:

- `ct126_short_mtf_riskoff_expected_r_top3`
- avg R: `0.4321`
- trades: `28`
- max DD: `0.74%`

It failed the `>=100` OOS trade gate. The same setup's expected-R top5 diagnostic had only `30`
trades, so increasing top-N did not solve sparsity.

Best broad-exposure probability comparators:

- short MTF risk-off probability top1: `889` trades, avg R `-0.3314`, max DD `81.04%`
- long MTF breakout probability top3: `871` trades, avg R `-0.1934`, max DD `68.15%`

Both failed positive expectancy and drawdown gates.

## Calibration And Ranking Findings

The probability threshold sweep selected validation-backed thresholds:

- short MTF risk-off: selected `p=0.50`
- short BTC/ETH below-MA: selected `p=0.55`
- long MTF breakout: selected `p=0.55`

Expected-R thresholds mostly fell back to `0.00` because the validation exposure floor rejected
sparser thresholds. The positive expected-R rows therefore remain useful as hypothesis hints, not
promotion evidence.

Top-N ranking did not create a stable working region:

- short MTF expected-R top1/top3/top5: `17`/`28`/`30` trades with positive avg R
- short probability top1/top2/top3/top5 diagnostics: `889`/`1190`/`1365`/`1546` trades, all negative
- long expected-R top1/top2/top3/top5: `40`/`59`/`75`/`89` trades, all negative
- long probability top1/top2/top3/top5: `564`/`764`/`871`/`979` trades, all negative

## Regime Findings

Regime stratification did not reveal a broad positive market pocket. The OOS candidate universe was
negative across major BTC/ETH shock, breadth, risk-on, and volatility buckets.

Examples:

- short MTF risk-off rule universe in `risk_off` band: avg R `-0.4049` over `3771` trades
- short BTC/ETH below-MA rule universe in `shock_down` BTC band: avg R `-0.2086` over `565` trades
- short BTC/ETH below-MA rule universe in `disorderly` volatility: avg R `-0.1750` over `465` trades
- long MTF breakout rule universe in `risk_on` band: avg R `-0.3169` over `2353` trades
- long MTF breakout rule universe in `disorderly` volatility: avg R `-0.1958` over `530` trades

These strata are less bad in places, but none reach positive broad exposure after costs.

## Interpretation

CT-126 changed the information set and preserved the stricter CT-125 calibration floor. The result
is informative but still a rejection:

- multi-timeframe OHLCV context is selected by the models, so it carries signal,
- that signal is not strong enough to produce `>=100` positive OOS trades,
- broad probability-ranked exposure remains economically bad after costs,
- continuing to tune OHLCV-only filters is unlikely to produce a robust paper-trading candidate.

The next hypothesis should add a genuinely different futures information set, such as funding,
open interest, taker buy/sell imbalance, liquidation pressure, or order-book/microstructure context,
if these fields are available point-in-time. If those data are unavailable, CT-113 should pause or
re-scope before more OHLCV-only model tuning.
