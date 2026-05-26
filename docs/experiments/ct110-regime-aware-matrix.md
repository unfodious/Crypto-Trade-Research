# CT-110 Regime-Aware Experiment Matrix

Date: 2026-05-26

## Scope

CT-110 runs the first controlled CT-107 experiment matrix after CT-109 added explicit
point-in-time regime features.

This is a new thesis test, not an expansion of the rejected CT-101/CT-102 threshold grids. The
matrix uses deterministic filters over features available at the decision timestamp and keeps the
same CT-96 expanded USD-M futures dataset, split dates, and cost assumptions so the result is
comparable with prior rejected evidence.

Generated local evidence:

- Matrix leaderboard: `data/generated/ct110_regime_aware_matrix/leaderboard.json`
- Matrix Markdown: `data/generated/ct110_regime_aware_matrix/leaderboard.md`

Committed configs:

- `configs/ct110-trend-continuation-regime-base.json`
- `configs/ct110-volatility-breakout-regime-base.json`
- `configs/ct110-regime-aware-matrix.json`

## Tested Setups

### H1: Trend-Aligned Continuation

The continuation setup extends the CT-102 high-volume long continuation idea with explicit local
trend agreement and a risk-off volatility abstention:

- `volume_zscore_20 >= 1.0`
- `return_1 >= 0.0`
- `trend_above_ma_20 == 1.0`
- `ma_slope_sign_20 >= 1.0`
- `volatility_bucket_20 <= 2.0`

The matrix tests 12-bar and 24-bar long labels with the same `0.4%` stop, `0.8%` target, and
`0.07%` total cost assumption used by the CT-102 family.

### H2: Trend-Filtered Volatility Breakout

The breakout setup retests expansion only when the candle is in an expanded, not disorderly,
volatility bucket and the local trend is compatible with a long breakout:

- `volatility_expansion_20 >= 1.3`
- `volatility_bucket_20 == 2.0`
- `close_location >= 0.7`
- `trend_above_ma_20 == 1.0`
- `ma_slope_sign_20 >= 0.0`

The matrix tests 12-bar and 24-bar long labels.

## Leaderboard

| Experiment | Decision | Model avg R | Rule avg R | Model trades | Max DD |
| --- | --- | ---: | ---: | ---: | ---: |
| `ct110_trend_continuation_regime_h12` | reject | -0.4921 | -0.4899 | 1,788 | 99.99% |
| `ct110_trend_continuation_regime_h24` | reject | -0.4675 | -0.4700 | 3,015 | 100.00% |
| `ct110_volatility_breakout_regime_h12` | reject | -0.5191 | -0.5544 | 805 | 98.68% |
| `ct110_volatility_breakout_regime_h24` | reject | -0.4451 | -0.5140 | 1,381 | 99.82% |

All four rows completed and all four registry records were written with `decision.status=reject`.

## Readout

The regime filters improved some rule-only comparisons but did not create a positive candidate:

- H1 12-bar was slightly worse than rule-only and H1 24-bar was only marginally less negative than
  rule-only.
- H2 improved versus rule-only at both horizons, with H2 24-bar the least-bad row, but the model
  remained deeply negative after costs.
- Drawdown remained near-total for every setup, so the deterministic local regime filters did not
  solve the CT-96 risk problem.
- Trade counts stayed meaningful, so the rejection is not merely a sample-size artifact.

## Decision

CT-110 does not produce a promoted candidate.

The least-bad row is `ct110_volatility_breakout_regime_h24`, but it is still rejected because:

- OOS model average R is negative at `-0.4451`.
- Max drawdown is `99.82%`, far above the `8%` gate.
- The promotion checklist still fails walk-forward, drawdown, stability, and paper-plan gates.

CT-111 should therefore apply stability and drawdown gates as a formal block/selection step rather
than attempt to prepare a paper-trading pack from this matrix.
