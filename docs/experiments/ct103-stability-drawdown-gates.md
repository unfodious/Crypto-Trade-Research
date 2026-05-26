# CT-103 Stability And Drawdown Gates

Date: 2026-05-26

## Scope

CT-103 adds promotion stability checks so a candidate cannot move toward paper trading because of
one lucky slice, a fragile threshold, or an unacceptable drawdown path.

Generated stability output stays ignored:

- `data/generated/ct103_stability_reports/ct102_volume_long_continuation_h24_stability_report.json`

Committed implementation:

- `src/crypto_trade_research/evaluation/stability.py`
- `tests/test_stability.py`

## Gates

The stability evaluator takes a candidate leaderboard row, nearby sensitivity rows, and a segment
breakdown, then emits `research.stability-report.v1`.

| Gate | Purpose |
| --- | --- |
| `positive_oos_expectancy` | Candidate must have positive model OOS average R. |
| `beats_rule_only_oos` | Candidate must beat deterministic rule-only OOS. |
| `minimum_trade_count` | Aggregate trade count must be meaningful. |
| `drawdown_within_limit` | Max drawdown must stay within configured depth limits. |
| `symbol_breadth` | Positive expectancy cannot be isolated to too few symbols. |
| `session_breadth` | Positive expectancy cannot be isolated to one coarse UTC session. |
| `lucky_day_concentration` | Positive expectancy cannot come from one lucky day. |
| `nearby_sensitivity` | Nearby threshold/horizon variants must remain positive often enough. |

Default CT-103 thresholds used for the CT-102 least-bad candidate:

- `max_drawdown_pct`: `0.08`
- `min_trade_count`: `100`
- `min_positive_symbol_fraction`: `0.50`
- `min_positive_session_fraction`: `0.50`
- `max_top_day_profit_share`: `0.75`
- `min_positive_nearby_fraction`: `0.50`

## Applied Candidate

Candidate: `ct102_volume_long_continuation_h24`

This was the least-bad CT-102 row:

- Model OOS average R: `-0.4576`
- Rule-only OOS average R: `-0.5360`
- Trades: `2,965`
- Max drawdown: `99.9999%`
- Artifact hash: `006aacf3f705b77c3fc4e9a98ae872231fc559ef251998056be5669938f63796`

## Stability Result

Status: `reject`

| Gate | Result | Detail |
| --- | --- | --- |
| `positive_oos_expectancy` | Fail | Model OOS average R was negative. |
| `beats_rule_only_oos` | Pass | The model beat rule-only, but both were negative. |
| `minimum_trade_count` | Pass | `2,965 >= 100`. |
| `drawdown_within_limit` | Fail | `99.9999%` exceeded the `8%` drawdown limit. |
| `symbol_breadth` | Fail | `0%` of symbol slices were positive. |
| `session_breadth` | Fail | `0%` of coarse UTC session slices were positive. |
| `lucky_day_concentration` | Fail | The only positive day represented `100%` of positive day expectancy. |
| `nearby_sensitivity` | Fail | `0%` of CT-102 nearby variants had positive model OOS average R. |

## Drawdown Attribution

The CT-102 segment breakdown showed the least-bad candidate was negative across all 11 symbols and
all coarse UTC sessions. The least-bad day, `2026-05-23`, was positive, but it was a single-day
pocket inside an otherwise negative validation/test path. The worst day was `2026-04-25`.

This means the blocker is not only aggregate drawdown. The candidate also lacks broad positive
symbol, session, day, and nearby-variant support.

## Decision

The CT-103 gates correctly reject `ct102_volume_long_continuation_h24` and would block CT-96
promotion even though it beat rule-only. A future candidate must pass these stability checks before
paper-trading pack preparation.
