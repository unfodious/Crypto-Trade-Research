# CT-127 Futures Microstructure Context Matrix

Date: 2026-05-27

Issue: CT-127

Epic: CT-113

## Decision

Rejected. CT-127 added point-in-time taker-flow microstructure features from the existing Binance
USD-M futures kline fields and ran the six-month controlled matrix. No candidate met the
paper-trading gates. Broad probability-ranked exposure had enough trades but stayed negative after
costs with excessive drawdown. Expected-R rows reduced drawdown but were also negative and below the
`>=100` OOS trade-count gate.

Backtests remain research evidence only. No paper-trading pack is approved.

## Data Feasibility

The current local storage and `research.dataset.v1` candle contract already include:

- `taker_buy_base_volume`
- `taker_buy_quote_volume`
- `number_of_trades`

These fields come from Binance futures kline data and are point-in-time after candle close.
Official Binance public-data docs list USD-M futures kline columns including quote volume, number of
trades, taker buy base volume, and taker buy quote volume:
`https://github.com/binance/binance-public-data`.

Current local storage does not contain canonical historical:

- funding rates
- open interest
- liquidation data
- order-book/depth snapshots
- long/short account or position ratios

Official Binance USD-M REST docs show:

- funding-rate history is available through `/fapi/v1/fundingRate` with `startTime`, `endTime`, and
  `limit` pagination: `https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History`
- open-interest statistics are available through `/futures/data/openInterestHist`, but the endpoint
  documents that only the latest one month is available:
  `https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics`
- taker buy/sell volume statistics are available through `/futures/data/takerlongshortRatio`, but
  the endpoint documents only the latest 30 days:
  `https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume`

Therefore CT-127 used the taker-flow fields already present in six-month kline history. Funding-rate
history is the next feasible external data branch; six-month OI and taker-long-short REST stats are
blocked unless a historical archive or paid/offline source is added.

## Hypothesis

Taker buy/sell pressure may capture short-lived aggressive flow better than OHLCV price structure
alone. If forced flow or aggressive participation contains edge, then a model should find better
selection among sell-pressure shorts and buy-pressure longs than the rejected OHLCV-only CT-126
matrix.

## Implementation

Added point-in-time microstructure features:

- `taker_buy_base_ratio`
- `taker_buy_quote_ratio`
- `taker_flow_imbalance`
- `taker_flow_imbalance_zscore_20`
- `taker_buy_base_ratio_mean_20`
- `trade_count_zscore_20`
- `market_taker_flow_imbalance`
- `btc_taker_flow_imbalance`
- `eth_taker_flow_imbalance`
- `relative_taker_flow_vs_btc`
- `relative_taker_flow_vs_eth`

The feature generator uses only current and prior closed candles. It also preserves CT-126 5m/15m
derived context in the full CT-127 feature set after Docker memory was increased.

Added unit coverage for:

- current and rolling taker-flow features
- same-timestamp market/BTC/ETH taker-flow context

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

Data availability check:

- rows: `2,867,040`
- rows with nonzero `volume`: `2,867,004`
- rows with nonzero `taker_buy_base_volume`: `2,864,777`
- taker buy base ratio mean: `0.50084`
- taker-flow imbalance mean: `0.00168`

## Matrix

Config:

- `configs/ct127-microstructure-context-base.json`
- `configs/ct127-microstructure-context-matrix.json`

Batch result: `8/8` completed, `0` failed.

Validation exposure floor: `50` trades.

Predeclared variants:

- short sell-pressure probability top3
- short sell-pressure expected-R top3/top5
- short sell-pressure plus risk-off expected-R top3
- short sell-pressure plus BTC/ETH sell-pressure expected-R top3
- long buy-pressure probability top3
- long buy-pressure expected-R top3
- long buy-pressure plus risk-on expected-R top3

## Results

| Experiment | Primary | Avg R | Rule Avg R | Trades | Max DD | Selected p | E[R] threshold | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| short sell-pressure probability top3 | probability | -0.2739 | -0.6224 | 2124 | 97.04% | 0.55 | 0.00 | reject |
| short sell-pressure expected-R top3 | expected-R | -0.3950 | -0.6224 | 50 | 4.87% | 0.55 | 0.00 | reject |
| short sell-pressure expected-R top5 | expected-R | -0.3950 | -0.6224 | 50 | 4.65% | 0.55 | 0.00 | reject |
| short sell-pressure risk-off expected-R top3 | expected-R | -0.0350 | -0.4507 | 50 | 1.81% | 0.55 | 0.00 | reject |
| short BTC/ETH sell-pressure expected-R top3 | expected-R | -0.4036 | -0.5983 | 35 | 1.06% | 0.55 | 0.00 | reject |
| long buy-pressure probability top3 | probability | -0.2158 | -0.6345 | 2277 | 94.94% | 0.55 | 0.00 | reject |
| long buy-pressure expected-R top3 | expected-R | -0.2454 | -0.6345 | 71 | 5.32% | 0.55 | 0.00 | reject |
| long buy-pressure risk-on expected-R top3 | expected-R | -0.2375 | -0.4897 | 64 | 2.83% | 0.55 | 0.00 | reject |

Least-bad primary row:

- `ct127_short_sell_pressure_riskoff_expected_r_top3`
- avg R: `-0.0350`
- trades: `50`
- max DD: `1.81%`

It failed positive expectancy and the `>=100` OOS trade-count gate.

Broad-exposure rows:

- short probability top3: `2124` trades, avg R `-0.2739`, max DD `97.04%`
- long probability top3: `2277` trades, avg R `-0.2158`, max DD `94.94%`

Both beat their terrible rule-only baselines but still failed positive expectancy and drawdown gates.

## Calibration And Ranking Findings

The probability threshold sweep selected `p=0.55` for all primary rows. Expected-R thresholds fell
back to `0.00` because sparser thresholds did not meet the validation exposure floor.

Top-N diagnostics did not reveal a pass:

- short sell-pressure probability top1/top2/top3/top5: all negative with `1477` to `2372` trades
- short risk-off expected-R top5 diagnostic: avg R `0.0795`, but only `55` trades
- long risk-on expected-R top1/top2 diagnostics: slightly positive, but only `45`/`58` trades

These are hypothesis hints only; they are too sparse and not stable enough for selection.

## Feature Findings

The model did use taker-flow fields. `taker_flow_imbalance` was the decision feature and appears in
the feature-importance output, and `taker_buy_quote_ratio`, `trade_count_zscore_20`, and MTF context
features were selected by ridge coefficients in several rows. But selection did not translate into a
positive, stable OOS trading candidate.

## Interpretation

CT-127 confirms that kline taker-flow has information, but not enough edge under the current
12-bar 2R stop/target framework after costs. The same pattern remains:

- broad exposure is negative and drawdown-heavy,
- expected-R ranking reduces exposure but still fails positive expectancy or trade count,
- OHLCV-derived and kline-derived taker-flow context are insufficient for CT-113 promotion.

The next branch should use a genuinely different external futures dataset. Funding-rate history is
the most feasible because Binance exposes historical funding rows with mark price through
`/fapi/v1/fundingRate`. Open interest and taker-long-short REST statistics are not immediately
usable for six-month research because the documented public endpoints only expose roughly the most
recent month.
