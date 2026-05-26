# Feature Engineering

The first feature library converts clean OHLCV candles into deterministic, point-in-time model features.

## Current Feature Groups

- Trend/regime: moving average, EMA, moving-average slope, trend-above-MA flag, MA-slope sign,
  MACD, DMI/ADX, volatility expansion, volatility bucket, distance from rolling high/low.
- Momentum: one-bar return, multi-bar ROC, RSI, stochastic close location, MACD histogram.
- Volatility: ATR, normalized ATR, realized volatility, Bollinger band position and width.
- Participation: rolling volume z-score and relative volume.
- Price action: candle body percentage, signed body pressure, wick ratios, wick pressure, close
  location, rolling range position, consecutive bull/bear bars.
- Market context: same-timestamp breadth, BTC/ETH reference regime, relative strength,
  correlation, and beta.
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

## Technical Indicator Features

CT-115 expands the feature library with technical-analysis-derived transforms. These features are
not trade rules by themselves; they measure market questions from the local indicator and
price-action playbooks:

- `ema_N`: smoothed trend location over the rolling close window.
- `rsi_N`: normalized momentum from rolling gains and losses.
- `stochastic_k_N`: close position inside the rolling high-low range, normalized from `0.0` to `1.0`.
- `atr_N` and `normalized_atr_N`: average true range and ATR divided by close.
- `bollinger_position_N` and `bollinger_width_N`: close position inside two-standard-deviation
  bands and normalized band width.
- `macd_N`, `macd_signal_N`, `macd_histogram_N`: rolling-window-derived MACD values using spans
  derived from `N`.
- `dmi_plus_N`, `dmi_minus_N`, `adx_N`: directional movement pressure and trend-strength proxy.
- `relative_volume_N`: current volume divided by rolling average volume.
- `realized_volatility_N`: standard deviation of close-to-close returns in the rolling window.
- `body_pressure`, `wick_pressure`, `consecutive_bull_bars`, `consecutive_bear_bars`: bar-by-bar
  auction pressure features.

Failure modes remain part of the feature contract. Trend indicators lag and whipsaw in ranges;
oscillators can stay extreme in strong trends; volume can be venue-specific; candle pressure needs
context. Use model validation and regime gates rather than treating any single indicator as an
authority.

## Market Context Features

CT-116 adds point-in-time market-context features using only rows available at the same decision
timestamp and prior rolling returns:

- `market_positive_return_fraction`: fraction of same-market symbols with positive one-bar return.
- `market_average_return_1`: average same-market one-bar return.
- `market_above_ma_fraction_N`: fraction of same-market symbols above their rolling mean.
- `risk_on_score_N`: simple breadth/reference trend composite from market breadth and BTC/ETH
  trend flags.
- `btc_return_1`, `eth_return_1`: reference one-bar returns at the same decision timestamp.
- `btc_trend_above_ma_N`, `eth_trend_above_ma_N`: reference trend state at the same timestamp.
- `btc_volatility_bucket_N`, `eth_volatility_bucket_N`: reference volatility bucket.
- `relative_strength_vs_btc_1`, `relative_strength_vs_eth_1`: symbol return minus reference
  return.
- `correlation_to_btc_N`, `beta_to_btc_N`, `correlation_to_eth_N`, `beta_to_eth_N`: rolling
  return relationship to BTC/ETH using only aligned historical return rows.

These features are designed for altcoin context: an alt setup should be allowed to know whether
BTC/ETH and the tracked universe are risk-on, risk-off, shocked, or divergent. Missing reference
rows produce `None`; the generator does not forward-fill future reference candles.

## Sample Run

```sh
make sample-features
```

This writes ignored files under `data/generated/sample_features/`:

- `features.parquet`
- `feature_manifest.json`

The manifest records feature names, groups, required lookback bars, and availability.
