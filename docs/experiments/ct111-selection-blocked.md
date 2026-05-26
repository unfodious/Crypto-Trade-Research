# CT-111 Stability Gates And Selection Block

Date: 2026-05-26

## Scope

CT-111 applies the CT-103 promotion gates to the CT-107 regime-aware candidate family after the
controlled CT-110 matrix.

This task decides whether any CT-110 row can be selected for paper-trading preparation. It does not
change runtime trading behavior and does not create a paper-trading pack.

## Evidence Reviewed

- Hypothesis document: `docs/experiments/ct108-regime-aware-hypothesis.md`
- Regime feature implementation: `src/crypto_trade_research/features/core.py`
- CT-110 matrix document: `docs/experiments/ct110-regime-aware-matrix.md`
- CT-110 leaderboard: `data/generated/ct110_regime_aware_matrix/leaderboard.json`
- Best-row registry record:
  `data/generated/experiment_registry/ct110_volatility_breakout_regime_h24/20260526T123100Z/record.json`

## Candidate Ranking

The CT-110 matrix completed four controlled regime-aware runs with no execution failures.

| Rank | Experiment | Decision | Model avg R | Rule avg R | Model trades | Max DD |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | `ct110_volatility_breakout_regime_h24` | reject | -0.4451 | -0.5140 | 1,381 | 99.82% |
| 2 | `ct110_trend_continuation_regime_h24` | reject | -0.4675 | -0.4700 | 3,015 | 100.00% |
| 3 | `ct110_trend_continuation_regime_h12` | reject | -0.4921 | -0.4899 | 1,788 | 99.99% |
| 4 | `ct110_volatility_breakout_regime_h12` | reject | -0.5191 | -0.5544 | 805 | 98.68% |

The least-bad row is `ct110_volatility_breakout_regime_h24` because it has the highest model OOS
average R and beats rule-only by `0.0689 R` per trade. It is still not eligible for selection.

## Gate Results

Applied CT-103/registry gates to `ct110_volatility_breakout_regime_h24`:

| Gate | Result | Evidence |
| --- | --- | --- |
| `positive_oos_expectancy` | Fail | Model OOS average R is `-0.4451`, below `0.0000`. |
| `beats_rule_only_oos` | Pass | Model beats rule-only: `-0.4451 > -0.5140`. |
| `minimum_trade_count` | Pass | Model OOS trades: `1,381 >= 100`. |
| `drawdown_within_limit` | Fail | Max drawdown is `99.82%`, above the `8%` gate. |
| `walk_forward_metrics_acceptable` | Fail | Walk-forward average R is `-0.4451`, below `0.0000`. |
| `nearby_sensitivity` | Fail | `0/4` CT-110 matrix rows have positive model OOS average R. |
| `stability_checks_pass` | Fail | Aggregate and nearby evidence are negative; no segment breakdown can rescue this row. |
| `paper_trading_plan_exists` | Fail | No paper plan should be attached for a rejected candidate. |

## Selection Decision

Status: `reject`

No CT-107 candidate is selected for paper trading.

`ct110_volatility_breakout_regime_h24` is blocked even though it beats rule-only because the model
is still negative after costs and suffers near-total drawdown. The entire CT-110 neighborhood is
negative, so there is no robust nearby variant to promote.

## Implications For CT-107

The first regime-aware layer improved some comparisons against rule-only but did not solve the core
problem observed in CT-96:

- explicit local trend/volatility filters are not sufficient on their own,
- long-only continuation/breakout remains structurally negative in the tested window,
- drawdown is the binding blocker before paper trading,
- the next iteration should change the risk model or add a broader market-reference/cooldown
  abstention layer before running another matrix.

CT-112 should record these lessons and update the research playbook. A paper-trading pack remains
blocked.
