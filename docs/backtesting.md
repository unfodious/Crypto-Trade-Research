# Backtesting

The first backtest layer evaluates precomputed research signals and model outcomes. It does not place orders, simulate exchange state, or modify live runtime behavior.

## Current Capabilities

- Rolling or anchored walk-forward split generation.
- Long and short signal evaluation.
- R-multiple cost model with fees, spread, slippage, and funding.
- Compounded fixed-risk sizing based on current equity.
- Trade event log with gross R, cost components, net R, size, PnL, and exit reason.
- Equity curve with drawdown.
- Metrics: total return, average R, expectancy, win rate, average win/loss, profit factor, max drawdown, drawdown duration, exposure, turnover, worst trade.

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
