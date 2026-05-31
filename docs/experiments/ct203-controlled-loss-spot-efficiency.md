# CT-203 controlled-loss exits for spot capital efficiency

Issue: `CT-203`
Epic: `CT-113`

## Question

CT-202 showed that strict no-loss exits create a structural spot-trading tradeoff: cash stays idle,
or positions get stuck with large unrealized losses. CT-203 tested whether small controlled-loss
exits solve that capital-efficiency problem.

This is a research-only re-scope. It does not change live trading, paper runtime, order placement,
leverage, or account behavior.

## Implementation

`spot_drawdown_swing` now supports two optional research-only exit controls:

- `emergency_stop_loss_pct`: closes a position when lifecycle return falls below a predefined loss;
- `loss_timeout_hours` plus `loss_timeout_exit_max_net_return_pct`: closes stale losing positions
  after a predefined age if they are still below the configured return threshold.

Portfolio reports also count `controlled_loss_exit_count`.

## Data

Broad true-spot Binance Data Vision klines from CT-194:

- 17 spot symbols.
- 30m full-path replay over `2024H2`, `2025H1`, `2025JulNov`.
- 15m secondary sanity check over the same windows.
- Round-trip cost: `0.20%`.

## 30m Results

Config:

- `configs/ct203-controlled-loss-spot-efficiency-30m.json`

Output:

- `data/generated/ct203_controlled_loss_spot_efficiency_30m/report.json`
- `data/generated/ct203_controlled_loss_spot_efficiency_30m/report.md`

| Scenario | Trades | Controlled loss exits | Open | Avg MTM | Avg closed | Max DD | Util | Avg monthly | PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ct203_dd4_strict_no_loss_baseline_1000` | 118 | 0 | 8 | 5.90% | 3.15% | -14.44% | 18.81% | 1.11% | inf |
| `ct203_dd4_emergency_stop6_1000` | 202 | 75 | 0 | 0.17% | 0.03% | -5.25% | 3.84% | 0.04% | 1.0102 |
| `ct203_dd4_emergency_stop8_1000` | 192 | 59 | 0 | 0.12% | 0.02% | -5.91% | 4.49% | 0.04% | 1.0072 |
| `ct203_dd4_timeout72_loss4_stop10_1000` | 189 | 55 | 0 | 0.21% | 0.03% | -6.38% | 4.68% | 0.06% | 1.0122 |

Controlled losses did solve the stuck-inventory symptom: all tested controlled-loss rows ended with
`0` open positions. But the economic edge disappeared. Profit factor stayed around `1.01`, average
closed return fell near zero, and average monthly return fell below `0.10%`.

## 15m Results

Config:

- `configs/ct203-controlled-loss-spot-efficiency-15m.json`

Output:

- `data/generated/ct203_controlled_loss_spot_efficiency_15m/report.json`
- `data/generated/ct203_controlled_loss_spot_efficiency_15m/report.md`

| Scenario | Trades | Controlled loss exits | Open | Avg MTM | Avg closed | Max DD | Util | Avg monthly | PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ct203_15m_dd4_strict_no_loss_baseline_1000` | 99 | 0 | 8 | 0.02% | 3.03% | -19.23% | 21.94% | 0.15% | inf |
| `ct203_15m_dd4_emergency_stop8_1000` | 179 | 64 | 0 | -6.02% | -1.01% | -8.37% | 2.51% | -1.03% | 0.6801 |

The secondary timeframe was worse. The controlled-loss row removed open inventory but turned the
system negative after costs.

## Decision

CT-203 is rejected as a paper-trading candidate.

Findings:

- Strict no-loss exits hide weak entry quality inside stuck open inventory.
- Controlled losses expose the weak edge: once losses are realized, PF falls to about `1.01` on 30m
  and below `1.0` on 15m.
- Controlled-loss exits reduce drawdown and remove open losers, but monthly return collapses far
  below the target.
- The current public OHLCV/taker-flow spot-entry family does not have enough entry edge for the
  user's monthly target, with or without small stop losses.

No live trading/runtime order placement changes were made.

CT-113 remains open.

## Next Hypothesis

The next CT-113 step should stop tuning this public OHLCV spot family and explicitly re-scope the
information source. Candidate paths:

- acquire or validate historical order-book / liquidation / richer derivatives data;
- test a different market structure idea only if it has a clear forced-flow thesis;
- otherwise pause CT-113 rather than continue threshold mining.

