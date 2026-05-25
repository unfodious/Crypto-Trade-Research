# Architecture

`crypto-trade-research` owns research workflows only. It exists to make market knowledge measurable before any production integration is considered.

## Boundaries

- Research repo: data contracts, feature engineering, labels, backtests, models, evaluation, reports, and artifacts.
- Runtime repo: Binance API calls, account state, fake/live executors, leverage, stops, take profit, reconciliation, and operator controls.
- Integration boundary: exported signals, ONNX/model artifacts, or a small inference service after explicit promotion gates.

## First-Version Strategy Shape

Strategies are ML-assisted, not fully autonomous:

1. Deterministic rules generate candidate setups.
2. Features describe regime, price action, indicators, volatility, participation, and risk context.
3. Supervised models estimate setup quality, expected R, and block conditions.
4. Deterministic risk rules decide eligibility and sizing outside the model.

## Promotion Principle

No model output can influence live execution until out-of-sample results, walk-forward reports, paper-trading evidence, rollback plans, and runtime safety gates are reviewed in YouTrack.
