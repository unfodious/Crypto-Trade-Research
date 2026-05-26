# Backtesting

The first backtest layer evaluates precomputed research signals and model outcomes. It does not place orders, simulate exchange state, or modify live runtime behavior.

## Current Capabilities

- Rolling or anchored walk-forward split generation.
- Long and short signal evaluation.
- R-multiple cost model with fees, spread, slippage, and funding.
- Compounded fixed-risk sizing based on current equity.
- Trade event log with gross R, cost components, net R, size, PnL, and exit reason.
- Optional signal `exit_time` for holding-window diagnostics.
- Equity curve with drawdown.
- Metrics: total return, average R, expectancy, win rate, average win/loss, profit factor, max drawdown, drawdown duration, exposure, turnover, worst trade, max concurrent positions, and max concurrent risk percentage.
- Research risk controls:
  - `max_trades_per_symbol` limits repeated entries in one symbol.
  - `max_trades_per_decision_time` ranks same-timestamp signals by confidence and keeps only the
    top candidates.
  - `loss_cooldown_signals` skips the next N candidate signals for a symbol after an accepted
    losing trade.

If `exit_time` is omitted, a signal is treated as an immediate realized R event for backward-compatible fixture tests. Use explicit `exit_time` before relying on concurrent exposure metrics.

Risk controls are research diagnostics, not live execution logic. They must be recomputed from
prior accepted trades or same-timestamp rankings only; do not use future PnL or labels to decide
whether a historical signal would have been eligible.

## Reports

Run:

```sh
make sample-backtest
```

The sample writes:

- `report.json`
- `trades.parquet`
- `equity_curve.parquet`
- `report.md`

## Interpretation

A backtest can reject a strategy quickly when it fails after costs, shows fragile expectancy, has too few trades, or depends on one historical path. It is not proof of live profitability. Promotion still requires out-of-sample checks, walk-forward stability, cost sensitivity, paper trading, monitoring, and runtime safety gates.
