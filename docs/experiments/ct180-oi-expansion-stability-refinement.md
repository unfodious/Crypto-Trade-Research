# CT-180 OI-Expansion Stability Refinement

Status: promoted to paper-trading/shadow candidate planning; no live approval.

CT-179 confirmed that abstaining from selected long trades when one-hour symbol open-interest
notional expands more than `1.5%` is useful, but rejected promotion because breadth was weak:
Europe was negative in every replay window, and symbol winners rotated across regimes.

CT-180 tests a predeclared stability refinement:

- keep the CT-179 OI expansion abstention;
- also abstain from Europe-session selected trades;
- preserve point-in-time futures metrics joins keyed by `symbol`, `timeframe`, and `decision_time`.

The selected family remains the frozen CT-145/CT-144 no-TON negative-funding long candidate. This is
research-only evidence and does not approve live trading.

## Implementation

Added selected-trade feature flags:

- `fm_session_asia`, `fm_session_europe`, `fm_session_us`;
- `fm_symbol_*` flags for the CT-113 universe;
- `fm_symbol_group_ada_icp_sui`;
- `fm_symbol_group_avax_sol`.

Extended the fast selected-trade screen and historical replay runner with optional filter groups.
Legacy `filters` remain an AND pattern. New `filter_groups` / `abstention_filter_groups` express
OR-of-AND patterns:

```json
[
  [
    {
      "feature": "fm_oi_value_change_1h",
      "operator": ">",
      "value": 0.015
    }
  ],
  [
    {
      "feature": "fm_session_europe",
      "operator": ">=",
      "value": 1
    }
  ]
]
```

Configs:

- `configs/ct180-futures-metrics-selected-features.json`;
- `configs/ct180-oi-expansion-stability-selected-matrix.json`;
- `configs/ct180-2024h2-oi-high-or-europe-replay.json`;
- `configs/ct180-2025h1-oi-high-or-europe-replay.json`;
- `configs/ct180-2025julnov-oi-high-or-europe-replay.json`.

Generated reports:

- `data/generated/ct180_oi_expansion_stability_selected_matrix/report.json`;
- `data/generated/ct180_2024h2_oi_high_or_europe_replay/replay_report.json`;
- `data/generated/ct180_2025h1_oi_high_or_europe_replay/replay_report.json`;
- `data/generated/ct180_2025julnov_oi_high_or_europe_replay/replay_report.json`.

## Selected-Trade Screen

The selected screen tested OI thresholds, Europe-only abstention, symbol-group exclusions, and
combined OI/session/crowding rules. The strongest stable row was:

`oi_high_or_europe`: abstain when `fm_oi_value_change_1h > 0.015` OR
`fm_session_europe >= 1`.

| Window | Trades | Avg R | Max DD | PF | Positive symbols | Positive sessions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024H2` | `643` | `0.1188` | `1.20%` | `1.2855` | `4 / 5` | `2 / 2` |
| `2025H1` | `1,250` | `0.0514` | `3.24%` | `1.1190` | `5 / 5` | `2 / 2` |
| `2025JulNov` | `643` | `0.0452` | `3.11%` | `1.0961` | `3 / 5` | `2 / 2` |

## Full Replay Results

Full replay matched the selected screen headline metrics.

| Window | Pre-filter selected | Kept selected | Trades | Avg R | Max DD | PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024H2` | `3,460` | `1,311` | `643` | `0.1188` | `1.20%` | `1.2855` |
| `2025H1` | `5,331` | `2,539` | `1,250` | `0.0514` | `3.24%` | `1.1190` |
| `2025JulNov` | `2,629` | `1,329` | `643` | `0.0452` | `3.11%` | `1.0961` |

Compared with CT-179 OI-only abstention:

| Window | CT-179 trades | CT-179 avg R | CT-179 DD | CT-180 trades | CT-180 avg R | CT-180 DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024H2` | `951` | `0.0633` | `1.92%` | `643` | `0.1188` | `1.20%` |
| `2025H1` | `1,703` | `0.0131` | `3.83%` | `1,250` | `0.0514` | `3.24%` |
| `2025JulNov` | `876` | `0.0172` | `3.11%` | `643` | `0.0452` | `3.11%` |

Compared with the base CT-145-family replay:

- H1 2025 improves from avg R `-0.0083` and DD `9.85%` to avg R `0.0514` and DD `3.24%`;
- all windows remain above the `>=100` trade floor;
- all windows beat no-trade on average R, while no-trade still has zero drawdown by definition;
- CT-180 trades less often than the base and CT-179 rows, but the stability gain is material.

## Stability

Symbol breadth:

| Window | Positive symbols | Detail |
| --- | ---: | --- |
| `2024H2` | `4 / 5` | `AVAX`, `ICP`, `SOL`, `SUI` positive; `ADA` negative |
| `2025H1` | `5 / 5` | all five symbols positive |
| `2025JulNov` | `3 / 5` | `ADA`, `AVAX`, `ICP` positive; `SOL`, `SUI` negative |

Session breadth after Europe abstention:

| Window | Asia | US |
| --- | ---: | ---: |
| `2024H2` | `0.0912` avg R over `259` trades | `0.1374` avg R over `384` trades |
| `2025H1` | `0.0410` avg R over `587` trades | `0.0606` avg R over `663` trades |
| `2025JulNov` | `0.0065` avg R over `363` trades | `0.0954` avg R over `280` trades |

## Gate Check

| Gate | Result |
| --- | --- |
| Positive avg R after costs in every replay window | pass |
| Beats no-trade on avg R | pass |
| Improves the CT-179 OI-only baseline | pass |
| `>=100` OOS trades per window | pass |
| Drawdown within gate | pass |
| At least `50%` positive symbol breadth per window | pass |
| At least `50%` positive session breadth per window | pass |
| Point-in-time futures metrics join | pass |
| Live-trading approval | fail by policy; not requested and not allowed |

## Decision

Promote CT-180 to a paper-trading/shadow candidate plan.

Do not approve live trading.

Do not claim a live working model. Backtests remain rejection/promotion evidence only, and this
candidate still needs forward/paper evidence under current market data.

Recommended paper-trading candidate rule:

- candidate: CT-145/CT-144 no-TON negative-funding long family;
- trade only when the frozen pack selects the trade;
- abstain if `fm_oi_value_change_1h > 0.015`;
- abstain if the decision timestamp is in Europe session (`08:00 <= UTC hour < 16:00`);
- keep existing pack risk controls and runtime safety gates;
- run paper/shadow only, no live orders.

## Next Step

Create a follow-up issue for a CT-180 paper-trading/shadow pack and monitor:

- generate a dry-run/paper pack with the CT-180 abstention rule;
- record the inference contract for required futures metrics and session flags;
- run a 30-day forward shadow monitor on the droplet;
- compare forward trades against the full-replay expectations before any live-trading discussion.
