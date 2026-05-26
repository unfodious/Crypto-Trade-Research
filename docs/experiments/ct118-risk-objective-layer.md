# CT-118 Risk Model And Objective Layer

Date: 2026-05-26

## Scope

CT-118 adds research-only risk controls and objective/ranking support for the CT-113 multifeature
model path. It does not change live trading runtime behavior.

## Implemented Controls

Backtest config now supports:

- `max_trades_per_symbol`: caps repeated accepted entries for one symbol.
- `max_trades_per_decision_time`: ranks same-timestamp model signals by confidence and keeps only
  the top N candidates.
- `loss_cooldown_signals`: after an accepted losing trade, skips the next N candidate signals for
  that symbol.

Baseline reports now include:

- `multifeature_ridge`
- `multifeature_ridge_oos`
- `multifeature_ridge_risk_controlled`
- `multifeature_ridge_risk_controlled_oos`

When `risk_controls` are configured, `multifeature_ridge_risk_controlled_oos` becomes the primary
strategy for registry and promotion gates. Without risk controls, `multifeature_ridge_oos` remains
primary.

## Objective Interpretation

CT-118 does not yet introduce a separate regression model, but it changes the objective layer in two
important ways:

- The multifeature model probability is now used as signal confidence, so same-timestamp `top-N`
  ranking is a first-class research objective.
- Registry metrics retain `single_feature_average_r`, allowing CT-119 to compare rule-only,
  single-feature, multifeature, and risk-controlled multifeature paths.

The next objective extension should add explicit expected-R ranking or regression only after the
CT-119 matrix shows whether confidence-ranked multifeature filtering has any positive OOS signal.

## Committed Config Seed

Committed CT-119-ready seed config:

- `configs/ct118-multifeature-risk-breakout-base.json`

This config uses the CT-96 expanded USD-M futures dataset, CT-115/CT-116 enriched features, a
BTC/ETH/breadth-aware breakout setup, and risk controls:

- `max_trades_per_symbol: 200`
- `max_trades_per_decision_time: 3`
- `loss_cooldown_signals: 2`

Generated outputs remain ignored under `data/generated/`.

## Safety Notes

These controls are research diagnostics. They do not place orders, cancel orders, resize positions,
change leverage, or alter runtime risk gates. A future paper-trading candidate still requires a
separate safety-reviewed runtime task before integration.
