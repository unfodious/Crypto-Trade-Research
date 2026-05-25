# Experiment Guidelines

Research decisions should survive costs, regime changes, and out-of-sample checks.

## Before Coding a Backtest

- State the market, venue, timeframe, holding period, and universe.
- Define the edge hypothesis in market-behavior terms, not only indicator crossings.
- Specify entries, exits, stops, sizing, no-trade states, fees, spread, slippage, and funding assumptions.
- Define what would invalidate the idea.

## Validation Ladder

1. Visual sanity check across known regimes.
2. Unit tests for feature, label, and metric calculations.
3. In-sample run with conservative assumptions.
4. Out-of-sample run not used for parameter selection.
5. Robustness checks across costs, delay, missing trades, and parameter ranges.
6. Walk-forward evaluation if parameters adapt.
7. Paper-trading plan before any runtime integration.

## Required Metrics

- Expectancy and average R.
- Drawdown depth and duration.
- Trade count, hit rate, average win, average loss, and profit factor.
- Exposure, turnover, capacity, and cost sensitivity.
- Regime-level performance and no-trade/block analysis.
