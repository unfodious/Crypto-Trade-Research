# CT-195 Spot Confirmed Reversal Breakout

Status: rejected for paper trading; useful selected-universe pocket found.

## Thesis

CT-195 tested whether spot entries should wait for proof that demand has returned after a drawdown,
rather than buying a coin only because it has dropped.

The new point-in-time entry layer requires a close above a recent local range after drawdown
exhaustion. Optional controls require relative volume and constrain the prior range width.

## Leakage Fix

Before running CT-195, the replay found a bug in the diagnostic timing helper:
`entry_profit_lookahead_hours = null` was incorrectly treated as "look ahead until the end of the
window" instead of "disable lookahead." This was fixed so no-lookahead rows now do not inspect
future highs.

The selected `30m` baseline remained the cleanest honest CT-194 comparison:

| Scenario | Avg return | 2024H1 | 2024H2 | 2025H1 | 2025JulNov | Avg max PnL DD | Closed | Open | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ct194_30m_baseline_guard_1000` | `2.69%` | `2.05%` | `1.93%` | `3.63%` | `3.14%` | `-0.88%` | `25` | `0` | fail |

## Selected Five-Symbol Results

Inputs:

- true Binance Spot `30m` OHLCV;
- symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`;
- windows: `2024H1`, `2024H2`, `2025H1`, `2025JulNov`;
- total portfolio cap: `$1000`;
- no future lookahead for CT-195 candidate rows.

Artifacts:

- `configs/ct195-spot-confirmed-reversal-breakout-30m-5sym.json`
- `data/generated/ct195_spot_confirmed_reversal_breakout_30m_5sym/report.json`

| Scenario | Avg return | 2024H1 | 2024H2 | 2025H1 | 2025JulNov | Avg max PnL DD | Closed | Open | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd8_breakout12_rvol15_guard_1000` | `0.00%` | `0.00%` | `0.00%` | `0.00%` | `0.00%` | `0.00%` | `0` | `0` | fail |
| `portfolio_dd6_breakout12_rvol13_guard_1000` | `1.38%` | `0.00%` | `0.00%` | `5.52%` | `0.00%` | `-2.24%` | `1` | `0` | fail |
| `portfolio_dd6_breakout6_guard_1000` | `4.65%` | `5.36%` | `1.96%` | `10.34%` | `0.94%` | `-3.27%` | `25` | `0` | fail |
| `portfolio_dd6_breakout6_sized125_guard_1000` | `6.83%` | `8.27%` | `3.27%` | `14.22%` | `1.56%` | `-4.71%` | `25` | `0` | pass |
| `portfolio_dd6_breakout6_sized150_guard_1000` | `8.20%` | `9.93%` | `3.93%` | `17.06%` | `1.87%` | `-5.64%` | `25` | `0` | pass |
| `portfolio_dd6_breakout6_target5_sized125_guard_1000` | `7.59%` | `10.24%` | `4.16%` | `14.42%` | `1.56%` | `-4.71%` | `25` | `0` | pass |

The useful part is real: waiting for a `DD6 + 6-bar breakout` produced a cleaner selected-universe
pocket than the CT-194 baseline, and increasing spot allocation within the same `$1000` cap cleared
the initial research gate.

The weakness is monthly distribution:

| Scenario | Strongest month | Weakest month | Inactive months |
| --- | ---: | ---: | ---: |
| `portfolio_dd6_breakout6_sized125_guard_1000` | `2025-03 +21.20%` | `2025-02 -7.10%` | `10` |
| `portfolio_dd6_breakout6_sized150_guard_1000` | `2025-03 +25.84%` | `2025-02 -8.52%` | `10` |
| `portfolio_dd6_breakout6_target5_sized125_guard_1000` | `2025-03 +21.18%` | `2025-02 -7.05%` | `10` |

This does not meet the user's desired month-sized return profile. It is a sparse swing pocket with
occasional strong months, not a consistent monthly compounding model.

## Broad 17-Symbol Validation

The same confirmed-breakout idea was then tested on the existing broad `30m` universe:

- `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`,
  `XRPUSDT`, `DOTUSDT`, `LINKUSDT`, `NEARUSDT`, `APTUSDT`, `ARBUSDT`, `OPUSDT`, `INJUSDT`,
  `DOGEUSDT`.

Artifacts:

- `configs/ct195-spot-confirmed-reversal-breakout-broad-30m.json`
- `data/generated/ct195_spot_confirmed_reversal_breakout_broad_30m/report.json`

| Scenario | Avg return | 2024H2 | 2025H1 | 2025JulNov | Avg max PnL DD | Closed | Open | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ct194_broad_30m_baseline_guard_1000` | `4.39%` | `4.20%` | `8.21%` | `0.75%` | `-4.21%` | `42` | `4` | fail |
| `portfolio_dd6_broad_breakout6_guard_1000` | `6.24%` | `5.43%` | `11.03%` | `2.28%` | `-4.93%` | `38` | `4` | fail |
| `portfolio_dd6_broad_breakout6_sized125_guard_1000` | `9.26%` | `9.43%` | `16.00%` | `2.34%` | `-7.03%` | `38` | `4` | fail |
| `portfolio_dd6_broad_breakout6_sized150_guard_1000` | `11.11%` | `11.31%` | `19.20%` | `2.81%` | `-8.36%` | `38` | `4` | fail |
| `portfolio_dd6_broad_breakout6_momentum_rotation_1000` | `6.76%` | `11.69%` | `7.92%` | `0.68%` | `-6.07%` | `31` | `1` | fail |
| `portfolio_dd6_broad_breakout6_momentum_rotation_sized125_1000` | `10.21%` | `18.11%` | `10.90%` | `1.64%` | `-9.05%` | `31` | `1` | fail |

Broad validation increases average return but reintroduces unresolved inventory. This means the
selected five-symbol result is not stable enough to promote.

## Decision

Do not approve live trading.

Do not claim a working model.

Do not prepare a paper-trading pack yet.

CT-195 found a useful entry improvement:

- confirmed breakout after drawdown is better than just buying the dip;
- within selected five symbols, `$125-$150` sizing under a `$1000` cap can clear the old research
  gate;
- broad universe replay shows the same idea has unresolved inventory risk.

CT-113 stays open. The next branch should keep the confirmed-breakout idea but solve the monthly
activity and inventory problem, likely by adding a sell/abstain rule for stale winners/failed
breakouts or a broader candidate pool with explicit no-open-inventory enforcement.
