# CT-197 Spot Taker-Flow Pressure

Status: rejected for paper trading; data path improved.

## Thesis

CT-197 tested whether spot drawdown-breakout entries improve when the breakout is confirmed by
aggressive buy pressure.

Economic idea: after a drawdown, a breakout with more buyer-initiated flow should be less likely to
be a weak bounce than a breakout where price rises on thin or neutral flow.

## Data Feasibility

Raw Binance Spot `aggTrades` archives are available, but they are too large for an immediate
full-window matrix:

- `SOLUSDT-aggTrades-2025-03.zip`: about `222 MB`;
- `SUIUSDT-aggTrades-2025-03.zip`: about `161 MB`.

For the first CT-197 pass, the replay used point-in-time taker-flow fields embedded in Binance spot
kline archives instead:

- `quote_volume`;
- `number_of_trades`;
- `taker_buy_base_volume`;
- `taker_buy_quote_volume`.

The spot kline downloader now preserves those fields instead of reducing candles to OHLCV only.
This keeps the full selected/broad matrix small while still testing buyer-pressure information that
was not available to CT-195/CT-196.

Generated datasets:

| Dataset | Rows | Missing files | Flow columns |
| --- | ---: | ---: | --- |
| `ct197_spot_5sym_2024h1_30m_flow_dataset` | `43,680` | `0` | yes |
| `ct197_spot_5sym_2024h2_30m_flow_dataset` | `44,160` | `0` | yes |
| `ct197_spot_5sym_2025h1_30m_flow_dataset` | `43,440` | `0` | yes |
| `ct197_spot_5sym_2025julnov_30m_flow_dataset` | `36,720` | `0` | yes |
| `ct197_spot_broad_2024h2_30m_flow_dataset` | `150,144` | `0` | yes |
| `ct197_spot_broad_2025h1_30m_flow_dataset` | `147,696` | `0` | yes |
| `ct197_spot_broad_2025julnov_30m_flow_dataset` | `124,848` | `0` | yes |

## Implementation

The spot replay now derives:

- `taker_buy_base_ratio = taker_buy_base_volume / volume`;
- `taker_flow_imbalance = 2 * taker_buy_base_ratio - 1`;
- `taker_buy_ratio_lift_12`, compared with the prior 12 bars;
- `trade_count_zscore_24`;
- `volume_zscore_24`.

New optional scenario gates:

- `min_taker_buy_base_ratio`;
- `min_taker_flow_imbalance`;
- `min_taker_buy_ratio_lift`;
- `min_trade_count_zscore`;
- `min_volume_zscore`.

Artifacts:

- `configs/ct197-spot-taker-flow-pressure-30m-5sym.json`
- `configs/ct197-spot-taker-flow-pressure-broad-30m.json`
- `data/generated/ct197_spot_taker_flow_pressure_30m_5sym/report.json`
- `data/generated/ct197_spot_taker_flow_pressure_broad_30m/report.json`

## Selected Five-Symbol Results

Universe: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`.

| Scenario | Avg return | 2024H1 | 2024H2 | 2025H1 | 2025JulNov | Avg max DD | Closed | Open | Weakest month | Negative months | Inactive months | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd6_breakout6_sized150_guard_1000` | `8.20%` | `9.93%` | `3.93%` | `17.06%` | `1.87%` | `-5.64%` | `25` | `0` | `-8.52%` | `3` | `14` | pass |
| `portfolio_dd6_breakout6_target5_sized125_guard_1000` | `7.59%` | `10.24%` | `4.16%` | `14.42%` | `1.56%` | `-4.71%` | `25` | `0` | `-7.05%` | `3` | `14` | pass |
| `portfolio_dd6_breakout6_sized125_guard_1000` | `6.83%` | `8.27%` | `3.27%` | `14.22%` | `1.56%` | `-4.71%` | `25` | `0` | `-7.10%` | `3` | `14` | pass |
| `ct197_selected_lift03_sized125_1000` | `5.28%` | `5.49%` | `1.24%` | `12.82%` | `1.56%` | `-4.71%` | `18` | `0` | `-7.10%` | `3` | `15` | fail |
| `ct197_selected_buy55_sized150_1000` | `4.01%` | `5.41%` | `1.48%` | `7.26%` | `1.87%` | `-3.01%` | `16` | `0` | `-0.68%` | `1` | `16` | fail |
| `ct197_selected_buy55_target5_sized125_1000` | `3.85%` | `5.49%` | `2.12%` | `6.22%` | `1.56%` | `-2.52%` | `16` | `0` | `-0.57%` | `1` | `16` | fail |
| `ct197_selected_buy55_sized125_1000` | `3.34%` | `4.51%` | `1.24%` | `6.05%` | `1.56%` | `-2.52%` | `16` | `0` | `-0.57%` | `1` | `16` | fail |
| `ct197_selected_lift03_trades05_sized125_1000` | `2.29%` | `0.99%` | `0.00%` | `8.16%` | `0.00%` | `-3.09%` | `4` | `0` | `-9.41%` | `2` | `20` | fail |
| `ct197_selected_buy60_sized125_1000` | `0.87%` | `2.24%` | `1.25%` | `0.00%` | `0.00%` | `-1.26%` | `4` | `0` | `0.00%` | `0` | `22` | fail |

Selected conclusion: taker-flow gates reduce weak months and drawdown in some rows, but they do it
mostly by removing trades. They do not beat the CT-195 selected rows and make the monthly activity
problem worse.

## Broad Seventeen-Symbol Results

| Scenario | Avg return | 2024H2 | 2025H1 | 2025JulNov | Avg max DD | Closed | Open | Avg open | Weakest month | Negative months | Inactive months | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd6_broad_breakout6_sized150_guard_1000` | `11.66%` | `11.31%` | `19.20%` | `4.46%` | `-8.36%` | `39` | `3` | `-7.77%` | `-7.91%` | `4` | `6` | fail |
| `portfolio_dd6_broad_breakout6_sized125_guard_1000` | `9.71%` | `9.43%` | `16.00%` | `3.72%` | `-7.03%` | `39` | `3` | `-7.77%` | `-6.61%` | `4` | `6` | fail |
| `ct196_broad_momentum_rank30_open4_failed12_stale72_sized125_1000` | `5.97%` | `7.76%` | `9.15%` | `1.00%` | `-7.45%` | `31` | `0` | `0.00%` | `-8.55%` | `3` | `8` | pass old gate |
| `ct197_broad_lift03_sized125_1000` | `5.78%` | `5.12%` | `12.82%` | `-0.60%` | `-7.70%` | `26` | `4` | `-7.43%` | `-6.51%` | `4` | `9` | fail |
| `ct197_broad_risk_lift03_sized125_1000` | `4.46%` | `5.37%` | `7.26%` | `0.74%` | `-7.08%` | `22` | `0` | `0.00%` | `-8.70%` | `3` | `11` | fail |
| `ct197_broad_buy55_sized150_1000` | `4.45%` | `5.45%` | `8.62%` | `-0.72%` | `-7.33%` | `24` | `4` | `-7.43%` | `-3.76%` | `3` | `10` | fail |
| `ct197_broad_buy55_sized125_1000` | `3.71%` | `4.54%` | `7.19%` | `-0.60%` | `-6.14%` | `24` | `4` | `-7.43%` | `-3.16%` | `3` | `10` | fail |
| `ct197_broad_risk_buy55_sized125_1000` | `2.16%` | `4.96%` | `0.76%` | `0.74%` | `-3.11%` | `20` | `0` | `0.00%` | `-0.45%` | `1` | `13` | fail |

Broad conclusion: taker-flow gates did not solve open inventory for the high-return rows and did
not improve the CT-196 no-open-risk row. The best no-open CT-197 risk row (`+4.46%`) is below the
CT-196 control row (`+5.97%`) and below CT-195 selected rows.

## Decision

Do not approve live trading.

Do not prepare a paper-trading pack.

Do not claim a working model.

CT-197 rejects kline-level taker-flow as a sufficient edge layer for the current spot
drawdown-breakout thesis. The data path is still valuable because future spot experiments can now
use point-in-time taker-flow fields cheaply.

CT-113 stays open. If we continue this branch, the next distinct hypothesis should use raw
`aggTrades` only around candidate decision windows, not full-month full-universe ingestion. That
would test large-trade clustering and aggressive-buyer bursts near entries without downloading
many GB of irrelevant trades.
