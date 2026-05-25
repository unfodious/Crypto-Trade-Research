# Feature Engineering

The first feature library converts clean OHLCV candles into deterministic, point-in-time model features.

## Current Feature Groups

- Regime: moving average, moving-average slope, volatility expansion, distance from rolling high/low.
- Indicator: one-bar return and multi-bar ROC.
- Participation: rolling volume z-score.
- Price action: candle body percentage, wick ratios, close location, rolling range position.
- Multi-timeframe: most recent higher-timeframe close and return, joined only when its `source_available_at` and `close_time` are not later than the base row decision time.

## Warmup Policy

Rows are preserved during warmup. Features that require unavailable history are `None`, and each row includes `warmup_missing_bars`.

## Availability

All initial features are `post_close`: they are valid only at or after the source candle close time. Feature generation must not read labels, realized PnL, future returns, future highs/lows, or higher-timeframe candles that have not closed.

## Sample Run

```sh
make sample-features
```

This writes ignored files under `data/generated/sample_features/`:

- `features.parquet`
- `feature_manifest.json`

The manifest records feature names, groups, required lookback bars, and availability.
