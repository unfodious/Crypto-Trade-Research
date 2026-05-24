# Crypto Trade Research

Research workspace for Crypto Trade ML experiments.

This repository is intentionally separate from `crypto-trade-infrastructure` and the Go `crypto-trade` backend. Keep exploratory Python dependencies, datasets, notebooks, backtest reports, and model artifacts here. The Go backend remains responsible for runtime execution, exchange integration, state synchronization, and live trading safety.

## Initial Direction

- Build reproducible market datasets.
- Engineer market-regime, price-action, indicator, volatility, participation, and multi-timeframe features.
- Create leakage-safe labels such as target-before-stop, expected R, MFE/MAE, and no-trade outcomes.
- Evaluate simple non-neural baselines before deep learning.
- Promote models only after out-of-sample and walk-forward evidence.

## Non-Goals

- No live trading execution from this repository.
- No secrets, API keys, raw credentials, or private production exports committed here.
- No direct neural-network authority over leverage, order size, or order submission.

See YouTrack epic `CT-34` for the implementation roadmap.
