"""Causal indicator maths, matching the Go analyzer's definitions.

`backend/internal/app/services/trade/analyzer/analyzer.go` computes RSI(14),
MACD(12,26,9), Bollinger(20, 2sd, SMA basis on 1h/4h/1d), ATR(20), ADX(14),
EMA(8/18/50/200) and Keltner(EMA20 +/- ATR). The same parameters are used here so
research and live cannot drift apart.

Every function returns a series aligned to its input index where value `i` uses
only rows `0..i`. Nothing here is centred, and nothing is fitted on the full
series, so a value can never depend on a later bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(values: pd.Series, span: int) -> pd.Series:
    return values.ewm(span=span, adjust=False, min_periods=span).mean()


def sma(values: pd.Series, window: int) -> pd.Series:
    return values.rolling(window, min_periods=window).mean()


def wilder(values: pd.Series, period: int) -> pd.Series:
    """Wilder smoothing, which is what go-talib uses for RSI/ATR/ADX."""
    return values.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    previous_close = close.shift(1)
    return pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    return wilder(true_range(high, low, close), period)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = wilder(delta.clip(lower=0.0), period)
    loss = wilder((-delta).clip(lower=0.0), period)
    relative_strength = gain / loss.replace(0.0, np.nan)
    result = 100.0 - 100.0 / (1.0 + relative_strength)
    return result.where(loss != 0.0, 100.0).where(gain.notna())


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    smoothed_tr = wilder(true_range(high, low, close), period).replace(0.0, np.nan)
    plus_di = 100.0 * wilder(plus_dm, period) / smoothed_tr
    minus_di = 100.0 * wilder(minus_dm, period) / smoothed_tr
    denominator = (plus_di + minus_di).replace(0.0, np.nan)
    directional_index = 100.0 * (plus_di - minus_di).abs() / denominator
    return wilder(directional_index.fillna(0.0), period)


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    signal_line = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, signal_line, line - signal_line


def bollinger(
    close: pd.Series, window: int = 20, deviations: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """SMA basis, matching the Go analyzer's choice for 1h/4h/1d periods."""
    middle = sma(close, window)
    spread = close.rolling(window, min_periods=window).std(ddof=0) * deviations
    return middle + spread, middle, middle - spread


def keltner(
    close: pd.Series, average_true_range: pd.Series, window: int = 20
) -> tuple[pd.Series, pd.Series]:
    basis = ema(close, window)
    return basis + average_true_range, basis - average_true_range


def donchian(high: pd.Series, low: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """Channel over the `window` bars STRICTLY BEFORE each bar.

    The shift is the point: a breakout rule that included the current bar's own
    high would be trivially satisfied by the bar that set the high.
    """
    return (
        high.rolling(window, min_periods=window).max().shift(1),
        low.rolling(window, min_periods=window).min().shift(1),
    )


def realized_volatility(close: pd.Series, window: int) -> pd.Series:
    return close.pct_change().rolling(window, min_periods=window).std(ddof=0)


def zscore(values: pd.Series, window: int) -> pd.Series:
    """Trailing z-score. Never fit on the full series - that would leak."""
    mean = values.rolling(window, min_periods=window).mean()
    deviation = values.rolling(window, min_periods=window).std(ddof=0)
    return (values - mean) / deviation.replace(0.0, np.nan)
