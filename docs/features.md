# Feature Engineering

The first feature library converts clean OHLCV candles into deterministic, point-in-time model features.

## Current Feature Groups

- Regime: moving average, moving-average slope, trend-above-MA flag, MA-slope sign, volatility
  expansion, volatility bucket, distance from rolling high/low.
- Indicator: one-bar return and multi-bar ROC.
- Participation: rolling volume z-score.
- Price action: candle body percentage, wick ratios, close location, rolling range position.
- Multi-timeframe: most recent higher-timeframe close and return, joined only when its `source_available_at` and `close_time` are not later than the base row decision time.

## Warmup Policy

Rows are preserved during warmup. Features that require unavailable history are `None`, and each row includes `warmup_missing_bars`.

## Availability

All initial features are `post_close`: they are valid only at or after the source candle close time. Feature generation must not read labels, realized PnL, future returns, future highs/lows, or higher-timeframe candles that have not closed.

## Regime Features

The first regime-aware layer for CT-107 adds numeric features that can be used by deterministic
candidate filters without label leakage:

- `trend_above_ma_N`: `1.0` when the close is at or above `ma_N`, otherwise `0.0`.
- `ma_slope_sign_N`: `-1.0`, `0.0`, or `1.0` from `ma_slope_N`.
- `volatility_bucket_N`: `0.0` compressed, `1.0` normal, `2.0` expanded, `3.0` disorderly, based
  only on the current candle range relative to the rolling average range.

Warmup rows use `None` until the rolling window and previous MA needed by the feature are available.
These fields are still `post_close`; they must not be treated as pre-candle signals.

## Sample Run

```sh
make sample-features
```

This writes ignored files under `data/generated/sample_features/`:

- `features.parquet`
- `feature_manifest.json`

The manifest records feature names, groups, required lookback bars, and availability.
