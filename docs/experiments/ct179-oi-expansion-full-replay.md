# CT-179 OI-Expansion Full Replay

Status: rejected for working-model promotion; useful signal confirmed; no live approval.

CT-178 imported Binance Data Vision USD-M futures metrics and found one promising selected-trade
screen for the CT-145 family: abstain from selected long trades when symbol open-interest notional
expanded more than `1.5%` over the prior hour.

CT-179 moves that screen into the full historical replay runner so the filter is applied after the
frozen model/ranking path and before backtest evaluation.

## Implementation

Extended `historical_holdout_replay` with optional external feature rows:

- `external_feature_rows_path`;
- `external_feature_required`.

The join is keyed by:

- `symbol`;
- `timeframe`;
- `decision_time`.

The replay fails fast if an `fm_*` abstention filter is configured without an external feature path,
or if a required selected row is missing from the external feature parquet. This keeps the futures
metrics filter point-in-time and prevents silent "missing means keep" behavior.

Configs:

- `configs/ct179-2024h2-oi-expansion-abstention-replay.json`;
- `configs/ct179-2025h1-oi-expansion-abstention-replay.json`;
- `configs/ct179-2025julnov-oi-expansion-abstention-replay.json`.

Filter:

```json
{
  "feature": "fm_oi_value_change_1h",
  "operator": ">",
  "value": 0.015
}
```

## Aggregate Results

| Window | Base trades | Base avg R | Base DD | CT-179 trades | CT-179 avg R | CT-179 DD | CT-179 PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024H2` | `1,511` | `0.1455` | `3.74%` | `951` | `0.0633` | `1.92%` | `1.1356` |
| `2025H1` | `2,242` | `-0.0083` | `9.85%` | `1,703` | `0.0131` | `3.83%` | `1.0272` |
| `2025JulNov` | `1,255` | `0.0287` | `4.34%` | `876` | `0.0172` | `3.11%` | `1.0361` |

The full replay exactly matched the CT-178 selected-trade screen headline metrics, which confirms
the screen was consistent with the replay path for this candidate.

Compared with the base CT-145-family replay:

- H1 2025 improves from negative to positive after costs;
- drawdown falls in all three historical windows;
- every window stays above the `>=100` trade floor;
- aggregate results beat no-trade on average R, but no-trade still has zero drawdown by definition.

Compared with CT-176 OHLCV-derived abstention, the OI rule is materially better on the H1 failure
window:

- CT-176 best CT-145 H1 row: `ct175_strict_eth_deleveraging`, `2,241` trades, avg R `-0.0010`,
  max DD `9.85%`;
- CT-179 OI rule H1 row: `1,703` trades, avg R `0.0131`, max DD `3.83%`.

## Stability Checks

Symbol breadth remains the blocker.

| Window | Positive symbols | Detail |
| --- | ---: | --- |
| `2024H2` | `3 / 5` | `AVAX`, `SOL`, `SUI` positive; `ADA`, `ICP` negative |
| `2025H1` | `2 / 5` | `AVAX`, `SOL` positive; `ADA`, `ICP`, `SUI` negative |
| `2025JulNov` | `3 / 5` | `ADA`, `ICP`, `SUI` positive; `AVAX`, `SOL` negative |

Session breadth is also imperfect:

| Window | Positive sessions | Negative session |
| --- | ---: | --- |
| `2024H2` | `2 / 3` | `europe` |
| `2025H1` | `2 / 3` | `europe` |
| `2025JulNov` | `2 / 3` | `europe` |

Lucky-day concentration is acceptable:

| Window | Days | Positive days | Top positive day share |
| --- | ---: | ---: | ---: |
| `2024H2` | `87` | `38` | `12.01%` |
| `2025H1` | `138` | `56` | `13.97%` |
| `2025JulNov` | `68` | `21` | `19.21%` |

## Decision

No working model claim.

No paper-to-live promotion.

Do not prepare a paper-trading pack yet.

Keep CT-113 open.

The OI-expansion abstention filter is the strongest CT-113 external-data signal so far, but the
candidate does not have enough symbol/session robustness for promotion. It should be refined rather
than discarded.

## Next Step

Create a follow-up issue to refine the OI-expansion candidate with predeclared stability fixes:

- evaluate symbol-specific exclusion or per-symbol thresholds for `ADA`, `ICP`, `SUI`, `AVAX`, and
  `SOL`;
- test a Europe-session abstention/threshold interaction;
- keep the OI feature point-in-time and require positive aggregate metrics, `>=100` trades, drawdown
  within gate, and at least `50%` positive symbol/session breadth in every historical window.
