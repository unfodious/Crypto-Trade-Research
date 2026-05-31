# CT-202 spot capital-utilization expansion

Issue: `CT-202`
Epic: `CT-113`

## Question

CT-194/CT-201 showed that several true-spot rows can be positive, but they are too slow and sparse
to approach the target monthly return. CT-202 tested whether lower drawdown thresholds and explicit
capital-utilization reporting can increase trade count and portfolio usage while keeping the
user-requested no-loss exit premise.

The tested premise remains:

- no live trading changes;
- no paper runtime changes;
- no leverage;
- no forced sell in loss, except that unrealized open inventory is still marked to market for
  research honesty.

## Implementation

`spot_drawdown_swing` now reports portfolio capital usage:

- `average_capital_utilization_pct`;
- `average_idle_cash_pct`;
- `max_capital_utilization_pct`;
- `average_open_position_count`;
- monthly utilization metrics inside each `monthly_returns` row.

This does not change entry/exit behavior. It only makes idle cash and stuck inventory visible.

## Data

Broad true-spot Binance Data Vision klines from CT-194:

- 17 symbols.
- 30m windows: `2024H2`, `2025H1`, `2025JulNov`.
- 15m secondary sanity check over the same windows.

## 30m Capital-Utilization Matrix

Config:

- `configs/ct202-spot-capital-utilization-30m.json`

Output:

- `data/generated/ct202_spot_capital_utilization_30m/report.json`
- `data/generated/ct202_spot_capital_utilization_30m/report.md`

The matrix lowered drawdown thresholds to `4%`, `5%`, and `6%`, but required rebound/breakout
confirmation, positive stale/failed-breakout exits, market guards, and DCA only after prior favorable
movement.

| Scenario | Trades | Avg MTM | Avg closed | Open unreal. | Max DD | Avg util | Avg monthly |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ct202_dd4_rebound_breakout_open4_sized100_1000` | 118 | 5.90% | 3.15% | -27.77% | -14.44% | 18.81% | 1.11% |
| `ct202_dd5_rebound_breakout_open4_sized100_1000` | 98 | 2.29% | 2.93% | -25.11% | -14.60% | 13.29% | 0.52% |
| `ct202_dd6_rebound_breakout_open4_sized125_1000` | 67 | 6.01% | 3.48% | -17.16% | -7.95% | 8.10% | 1.11% |
| `ct202_dd4_rebound_breakout_open5_sized75_1000` | 146 | 4.69% | 2.83% | -24.61% | -13.04% | 15.41% | 0.87% |

The wider/lower-threshold rows increased trade count, but did not solve capital efficiency. Even the
most active row averaged only `18.81%` utilization, and the extra utilization came with large
unrealized open losses.

## 30m Anti-Stuck Matrix

Config:

- `configs/ct202-spot-capital-utilization-anti-stuck-30m.json`

Output:

- `data/generated/ct202_spot_capital_utilization_anti_stuck_30m/report.json`
- `data/generated/ct202_spot_capital_utilization_anti_stuck_30m/report.md`

Anti-stuck variants removed DCA and added stricter market-trend / relative-strength filters.

| Scenario | Trades | Avg MTM | Avg closed | Open unreal. | Max DD | Avg util | Avg monthly |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ct202_dd4_no_dca_market_trend_open4_sized100_1000` | 44 | 1.36% | 2.75% | -37.46% | -3.44% | 4.45% | 0.23% |
| `ct202_dd5_no_dca_market_trend_open4_sized125_1000` | 27 | 1.04% | 2.27% | -33.88% | -4.37% | 2.16% | 0.19% |
| `ct202_dd4_entry_rank72_no_dca_open4_sized100_1000` | 14 | 0.53% | 3.84% | -33.88% | -1.54% | 0.29% | 0.09% |

These rows reduced drawdown, but only by making the portfolio mostly idle. They still left deep
unrealized losers when positions got stuck.

## 15m Secondary Check

Config:

- `configs/ct202-spot-capital-utilization-15m.json`

Output:

- `data/generated/ct202_spot_capital_utilization_15m/report.json`
- `data/generated/ct202_spot_capital_utilization_15m/report.md`

| Scenario | Trades | Avg MTM | Avg closed | Open unreal. | Max DD | Avg util | Avg monthly |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ct202_15m_dd4_rebound_breakout_open4_sized100_1000` | 99 | 0.02% | 3.03% | -25.87% | -19.23% | 21.94% | 0.15% |
| `ct202_15m_dd4_no_dca_market_trend_open4_sized100_1000` | 25 | -0.52% | 2.92% | -41.33% | -3.95% | 3.17% | -0.08% |

15m did not rescue the idea. More frequent bars produced similar stuck-inventory behavior and worse
portfolio-level results.

## Decision

CT-202 is rejected as a paper-trading candidate.

The result is clear:

- Lowering drawdown thresholds can raise trade count above `100`, but creates large marked-to-market
  inventory risk.
- Anti-stuck filters reduce drawdown, but mostly by returning to idle cash.
- Under a strict no-loss exit premise, stuck inventory is not a minor implementation detail; it is
  the core risk model.
- The best average monthly result here is about `1.11%`, far below the target and still paired with
  unacceptable open-inventory drawdown.

No live trading/runtime order placement changes were made.

CT-113 remains open.

## Next Hypothesis

The next branch should explicitly test whether a controlled-loss exit is required for capital
efficiency. This is a research re-scope question, not a live-trading change:

- compare strict no-loss exits against small predefined emergency exits;
- measure whether accepting small realized losses lowers stuck-inventory drawdown and increases
  monthly compounding;
- keep spot-only and no leverage;
- do not approve live trading unless the user explicitly accepts the changed risk premise and paper
  evidence passes.

