"""Causal feature construction on a 4h decision grid with 1d context.

Leakage contract (asserted by `tests/test_edge_study_leakage.py`):

1. A row is keyed by `decision_time`, the moment the 4h bar CLOSED. Every value
   in that row is a function of bars that had already closed by then.
2. Higher-timeframe context is joined with `merge_asof` on the daily bar's own
   CLOSE time, so the partially formed daily bar is never visible.
3. All indicators are trailing (see `indicators.py`); there is no centred window
   and no scaler or statistic fitted over the whole series.
4. Cross-sectional context (BTC regime) is joined on the same decision grid and
   likewise uses only closed BTC bars.
5. Non-price context (funding, open interest, book depth) is joined by
   `altdata.attach_alt_features` on each source's own `known_at` time, again
   with a backward `merge_asof`. See `altdata` for the per-source publication
   lags and for why liquidations are a proxy rather than a feed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_trade_research.edge_study import altdata as alt_data
from crypto_trade_research.edge_study import indicators as ind

DONCHIAN_WINDOW = 20
ATR_PERIOD = 20
VOLATILITY_WINDOW = 30


def _timeframe_delta(timeframe: str) -> pd.Timedelta:
    return pd.Timedelta(timeframe)


def base_frame(bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Indicator frame for one timeframe, indexed by bar open time."""
    frame = pd.DataFrame(index=bars.index)
    close, high, low = bars["close"], bars["high"], bars["low"]

    frame["close"] = close
    frame["high"] = high
    frame["low"] = low
    frame["open"] = bars["open"]
    frame["atr"] = ind.atr(high, low, close, ATR_PERIOD)
    frame["atr_pct"] = frame["atr"] / close
    frame["rsi"] = ind.rsi(close, 14)
    frame["adx"] = ind.adx(high, low, close, 14)

    ema_short, ema_middle = ind.ema(close, 8), ind.ema(close, 18)
    ema_long, ema_very_long = ind.ema(close, 50), ind.ema(close, 200)
    frame["ema_short_rel"] = ema_short / close - 1.0
    frame["ema_long_rel"] = ema_long / close - 1.0
    frame["ema_stack"] = np.sign(ema_short - ema_middle) + np.sign(ema_long - ema_very_long)
    frame["ema_long_slope"] = ema_long.pct_change(5)

    macd_line, macd_signal, macd_hist = ind.macd(close)
    frame["macd_hist_norm"] = macd_hist / frame["atr"].replace(0.0, np.nan)
    frame["macd_above_signal"] = (macd_line > macd_signal).astype(float)

    upper, middle, lower = ind.bollinger(close)
    width = (upper - lower).replace(0.0, np.nan)
    frame["boll_position"] = (close - lower) / width
    frame["boll_width"] = width / middle

    keltner_upper, keltner_lower = ind.keltner(close, frame["atr"])
    frame["keltner_position"] = (close - keltner_lower) / (
        (keltner_upper - keltner_lower).replace(0.0, np.nan)
    )

    channel_high, channel_low = ind.donchian(high, low, DONCHIAN_WINDOW)
    frame["donchian_high"] = channel_high
    frame["donchian_low"] = channel_low
    span = (channel_high - channel_low).replace(0.0, np.nan)
    frame["donchian_position"] = (close - channel_low) / span
    frame["donchian_span_atr"] = span / frame["atr"].replace(0.0, np.nan)

    frame["return_1"] = close.pct_change(1)
    frame["return_6"] = close.pct_change(6)
    frame["return_30"] = close.pct_change(30)
    frame["realized_vol"] = ind.realized_volatility(close, VOLATILITY_WINDOW)
    frame["vol_of_vol"] = ind.zscore(frame["realized_vol"], 60)
    frame["atr_pct_z"] = ind.zscore(frame["atr_pct"], 60)

    # Participation. taker_buy_quote_volume is the aggressive-buy share of turnover.
    quote_volume = bars["quote_volume"].replace(0.0, np.nan)
    frame["taker_buy_share"] = bars["taker_buy_quote_volume"] / quote_volume
    frame["volume_z"] = ind.zscore(bars["quote_volume"], 60)
    frame["trade_size_z"] = ind.zscore(quote_volume / bars["count"].replace(0.0, np.nan), 60)

    body = (close - bars["open"]).abs()
    bar_range = (high - low).replace(0.0, np.nan)
    frame["body_fraction"] = body / bar_range
    frame["upper_wick"] = (high - close.combine(bars["open"], max)) / bar_range
    frame["lower_wick"] = (close.combine(bars["open"], min) - low) / bar_range

    frame["decision_time"] = frame.index + _timeframe_delta(timeframe)
    return frame


# `ema_stack` is deliberately absent: on the daily grid it needs EMA(200), i.e.
# 200 days of warm-up, which would discard nearly a third of the alt sample for
# one feature. EMA(50) context (`ema_long_rel`) costs 50 days and carries the
# same regime information.
DAILY_CONTEXT = [
    "rsi",
    "adx",
    "atr_pct",
    "ema_long_rel",
    "ema_long_slope",
    "donchian_position",
    "return_6",
    "realized_vol",
]


def build_features(
    bars_4h: pd.DataFrame,
    bars_1d: pd.DataFrame,
    btc_1d: pd.DataFrame | None = None,
    alt: alt_data.AltPanels | None = None,
) -> pd.DataFrame:
    """Return a 4h feature frame indexed by bar open time, with `decision_time`.

    `alt` carries the pair's non-price panels. When it is None every non-price
    column is still present and all-NaN, so the frame's shape does not depend on
    whether an archive happened to exist.
    """
    frame = base_frame(bars_4h, "4h")
    daily = base_frame(bars_1d, "1D")

    daily_context = daily[["decision_time", *DAILY_CONTEXT]].rename(
        columns={name: f"d1_{name}" for name in DAILY_CONTEXT}
    )
    merged = pd.merge_asof(
        frame.sort_values("decision_time"),
        daily_context.sort_values("decision_time"),
        on="decision_time",
        direction="backward",
        allow_exact_matches=True,
    )
    merged.index = frame.index

    if btc_1d is not None:
        btc = base_frame(btc_1d, "1D")
        btc_context = btc[["decision_time", "ema_long_rel", "realized_vol", "return_6"]].rename(
            columns={
                "ema_long_rel": "btc_ema_long_rel",
                "realized_vol": "btc_realized_vol",
                "return_6": "btc_return_6",
            }
        )
        merged = pd.merge_asof(
            merged.sort_values("decision_time"),
            btc_context.sort_values("decision_time"),
            on="decision_time",
            direction="backward",
            allow_exact_matches=True,
        )
        merged.index = frame.index

    merged["hour_of_day"] = merged.index.hour
    merged["day_of_week"] = merged.index.dayofweek
    return alt_data.attach_alt_features(merged, alt)


PRICE_FEATURE_COLUMNS = [
    "atr_pct",
    "atr_pct_z",
    "rsi",
    "adx",
    "ema_short_rel",
    "ema_long_rel",
    "ema_stack",
    "ema_long_slope",
    "macd_hist_norm",
    "macd_above_signal",
    "boll_position",
    "boll_width",
    "keltner_position",
    "donchian_position",
    "donchian_span_atr",
    "return_1",
    "return_6",
    "return_30",
    "realized_vol",
    "vol_of_vol",
    "taker_buy_share",
    "volume_z",
    "trade_size_z",
    "body_fraction",
    "upper_wick",
    "lower_wick",
    "d1_rsi",
    "d1_adx",
    "d1_atr_pct",
    "d1_ema_long_rel",
    "d1_ema_long_slope",
    "d1_donchian_position",
    "d1_return_6",
    "d1_realized_vol",
    "btc_ema_long_rel",
    "btc_realized_vol",
    "btc_return_6",
    "hour_of_day",
    "day_of_week",
]

#: Non-price inputs. Kept as a separate list so the study can be run on the
#: price set alone, the non-price set alone, or both - an ablation, not a
#: feature dump. 16 columns on top of 39 is already generous against the six to
#: eight independent regimes this window contains.
ALT_FEATURE_COLUMNS = list(alt_data.ALT_FEATURE_COLUMNS)

ALL_FEATURE_COLUMNS = [*PRICE_FEATURE_COLUMNS, *ALT_FEATURE_COLUMNS]

#: Default feature set. `tests/test_edge_study_leakage.py` asserts its causality
#: column by column, so anything added here inherits the leakage guarantee.
FEATURE_COLUMNS = ALL_FEATURE_COLUMNS

FEATURE_SETS = {
    "all": ALL_FEATURE_COLUMNS,
    "price": PRICE_FEATURE_COLUMNS,
    "alt": ALT_FEATURE_COLUMNS,
}


def feature_columns(name: str) -> list[str]:
    """Named feature set, for the study's `--feature-set` switch."""
    try:
        return list(FEATURE_SETS[name])
    except KeyError as error:
        raise ValueError(f"unknown feature set {name!r}: {sorted(FEATURE_SETS)}") from error
