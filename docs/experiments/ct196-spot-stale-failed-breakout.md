# CT-196 Spot Stale And Failed-Breakout Controls

Status: rejected for paper trading; useful inventory-control evidence found.

## Thesis

CT-196 tested whether the CT-195 confirmed-breakout spot pocket could become more usable by freeing
capital from positions that did not follow through.

The rules stayed point-in-time and spot-style:

- keep the `DD6 + 6-bar breakout` entry layer from CT-195;
- do not sell losing spot inventory just to make a backtest look cleaner;
- exit a failed breakout only if the lifecycle return is breakeven or positive after fees;
- exit stale positions only at breakeven or positive after fees;
- block DCA until the position has first shown some favorable excursion;
- apply a symbol cooldown after failed/stale breakeven exits.

## Implementation

The replay engine now reports explicit portfolio exit reasons:

- `profit_fade`;
- `trailing_stop`;
- `rotation_redeploy`;
- `failed_breakout_breakeven`;
- `stale_breakeven`.

New scenario controls:

- `failed_breakout_hold_hours`;
- `min_failed_breakout_followthrough_pct`;
- `failed_breakout_exit_min_net_return_pct`;
- `stale_exit_hold_hours`;
- `stale_exit_min_net_return_pct`;
- `failed_breakout_cooldown_hours`;
- `min_favorable_before_dca_pct`.

This is research-only code. It does not place, cancel, resize, or approve live orders.

Artifacts:

- `configs/ct196-spot-stale-failed-breakout-30m-5sym.json`
- `configs/ct196-spot-stale-failed-breakout-broad-30m.json`
- `data/generated/ct196_spot_stale_failed_breakout_30m_5sym/report.json`
- `data/generated/ct196_spot_stale_failed_breakout_broad_30m/report.json`

## Selected Five-Symbol Results

Universe: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`.

Windows: `2024H1`, `2024H2`, `2025H1`, `2025JulNov`.

| Scenario | Avg return | 2024H1 | 2024H2 | 2025H1 | 2025JulNov | Avg max DD | Closed | Open | Weakest month | Negative months | Inactive months | Exit mix |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd6_breakout6_sized125_guard_1000` | `6.83%` | `8.27%` | `3.27%` | `14.22%` | `1.56%` | `-4.71%` | `25` | `0` | `-7.10%` | `3` | `13` | `profit_fade=25` |
| `portfolio_dd6_breakout6_sized150_guard_1000` | `8.20%` | `9.93%` | `3.93%` | `17.06%` | `1.87%` | `-5.64%` | `25` | `0` | `-8.52%` | `3` | `13` | `profit_fade=25` |
| `portfolio_dd6_breakout6_target5_sized125_guard_1000` | `7.59%` | `10.24%` | `4.16%` | `14.42%` | `1.56%` | `-4.71%` | `25` | `0` | `-7.05%` | `3` | `13` | `profit_fade=25` |
| `ct196_failed12_stale72_sized125_1000` | `4.93%` | `5.37%` | `2.35%` | `10.46%` | `1.56%` | `-4.42%` | `25` | `0` | `-7.89%` | `3` | `13` | `failed=3, profit=15, stale=7` |
| `ct196_failed24_stale96_sized125_1000` | `5.02%` | `5.33%` | `2.72%` | `10.47%` | `1.56%` | `-4.42%` | `25` | `0` | `-7.88%` | `3` | `13` | `failed=5, profit=16, stale=4` |
| `ct196_failed12_stale72_strictdca_sized125_1000` | `3.37%` | `5.05%` | `2.35%` | `4.53%` | `1.56%` | `-2.51%` | `25` | `0` | `-2.11%` | `2` | `13` | `failed=3, profit=15, stale=7` |
| `ct196_failed12_stale72_target5_sized125_1000` | `5.20%` | `5.37%` | `3.23%` | `10.66%` | `1.56%` | `-4.40%` | `25` | `0` | `-7.84%` | `3` | `13` | `failed=3, profit=15, stale=7` |
| `ct196_failed12_stale72_sized150_1000` | `5.92%` | `6.44%` | `2.81%` | `12.55%` | `1.87%` | `-5.29%` | `25` | `0` | `-9.48%` | `3` | `13` | `failed=3, profit=15, stale=7` |

Selected-universe conclusion: failed/stale exits reduce some time risk and drawdown, but they also
cut winners before the old CT-195 rows. They do not fix sparse monthly activity and remain below the
user's desired monthly compounding profile.

## Broad Seventeen-Symbol Results

Universe: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`,
`ATOMUSDT`, `XRPUSDT`, `DOTUSDT`, `LINKUSDT`, `NEARUSDT`, `APTUSDT`, `ARBUSDT`, `OPUSDT`,
`INJUSDT`, `DOGEUSDT`.

Windows: `2024H2`, `2025H1`, `2025JulNov`.

| Scenario | Avg return | 2024H2 | 2025H1 | 2025JulNov | Avg max DD | Closed | Open | Avg open | Weakest month | Negative months | Inactive months | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd6_broad_breakout6_sized125_guard_1000` | `9.26%` | `9.43%` | `16.00%` | `2.34%` | `-7.03%` | `38` | `4` | `-5.66%` | `-6.61%` | `4` | `5` | fail |
| `portfolio_dd6_broad_breakout6_sized150_guard_1000` | `11.11%` | `11.31%` | `19.20%` | `2.81%` | `-8.36%` | `38` | `4` | `-5.66%` | `-7.91%` | `4` | `5` | fail |
| `portfolio_dd6_broad_breakout6_momentum_rotation_sized125_1000` | `10.21%` | `18.11%` | `10.90%` | `1.64%` | `-9.05%` | `31` | `1` | `-9.52%` | `-6.81%` | `5` | `7` | fail |
| `ct196_broad_failed24_stale96_sized125_1000` | `7.78%` | `7.55%` | `12.96%` | `2.82%` | `-5.94%` | `42` | `1` | `-14.58%` | `-7.16%` | `3` | `5` | fail |
| `ct196_broad_failed12_stale72_sized150_1000` | `8.25%` | `6.24%` | `15.42%` | `3.08%` | `-7.13%` | `42` | `1` | `-14.58%` | `-8.51%` | `4` | `5` | fail |
| `ct196_broad_momentum_failed12_stale72_sized125_1000` | `5.44%` | `6.95%` | `8.36%` | `1.00%` | `-6.90%` | `28` | `0` | `0.00%` | `-8.61%` | `4` | `7` | pass old gate only |
| `ct196_broad_momentum_rank30_open4_failed12_stale72_sized125_1000` | `5.97%` | `7.76%` | `9.15%` | `1.00%` | `-7.45%` | `31` | `0` | `0.00%` | `-8.55%` | `3` | `7` | pass old gate only |
| `ct196_broad_momentum_rank30_failed12_stale72_sized150_1000` | `6.53%` | `8.34%` | `10.03%` | `1.20%` | `-8.24%` | `28` | `0` | `0.00%` | `-10.34%` | `4` | `7` | pass old gate only |

The best CT-196 risk-control row is
`ct196_broad_momentum_rank30_open4_failed12_stale72_sized125_1000`:

- average window return: `+5.97%`;
- windows: `+7.76%`, `+9.15%`, `+1.00%`;
- closed trades: `31`;
- open positions: `0`;
- average max DD: `-7.45%`.

That is useful, but not enough. It does not beat the CT-195 selected rows (`+6.83%` to `+8.20%`),
still has `3` negative months and `7` inactive months, and is far below the desired month-sized
return profile.

## Decision

Do not approve live trading.

Do not prepare a paper-trading pack.

Do not claim a working model.

CT-196 confirms that failed/stale breakeven exits can control inventory without violating the
spot-only "do not sell in loss" constraint. The cost is that many exits are small breakeven releases,
so the model becomes safer but not materially more profitable.

CT-113 stays open. The next useful branch should not be another nearby OHLCV threshold sweep. It
should add a different information set, preferably point-in-time spot trade-flow or order-book
pressure around drawdown/breakout candidates.
