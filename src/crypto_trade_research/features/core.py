"""Point-in-time OHLCV feature engineering primitives."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

SCHEMA_VERSION = "research.dataset.v1"
GENERATOR_NAME = "crypto_trade_research.ohlcv_features"
REFERENCE_SYMBOLS = ("BTCUSDT", "ETHUSDT")


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    feature_set_version: str
    rolling_window: int = 20
    higher_timeframes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    group: str
    lookback_bars: int
    availability: str
    description: str


@dataclass(frozen=True, slots=True)
class FeatureManifest:
    schema_version: str
    feature_set_version: str
    generator_name: str
    row_count: int
    features: tuple[FeatureSpec, ...]


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    rows: list[dict[str, object]]
    manifest: FeatureManifest


def generate_ohlcv_features(
    rows: Sequence[dict[str, object]],
    config: FeatureConfig,
    higher_timeframe_rows: Sequence[dict[str, object]] | None = None,
    funding_rate_rows: Sequence[dict[str, object]] | None = None,
) -> FeatureFrame:
    """Generate deterministic, post-close OHLCV features from clean candle rows."""

    if config.rolling_window < 2:
        raise ValueError("rolling_window must be at least 2")
    if not rows:
        raise ValueError("rows must not be empty")

    sorted_rows = sorted(rows, key=_sort_key)
    higher_rows = sorted(higher_timeframe_rows or [], key=_sort_key)
    funding_rows = sorted(funding_rate_rows or [], key=_funding_sort_key)
    output_rows: list[dict[str, object]] = []
    for group_rows in _group_rows(sorted_rows):
        base_group_key = _base_group_key(group_rows[0])
        group_higher_rows = [
            row for row in higher_rows if _higher_timeframe_group_key(row) == base_group_key
        ]
        group_output_rows = [
            _build_feature_row(group_rows, index, config, group_higher_rows)
            for index in range(len(group_rows))
        ]
        _add_derived_multi_timeframe_features(group_output_rows, group_rows, config)
        _add_funding_features(group_output_rows, funding_rows, config.rolling_window)
        output_rows.extend(group_output_rows)

    _add_market_context_features(output_rows, config.rolling_window)
    _add_multi_timeframe_market_context_features(output_rows, config)

    return FeatureFrame(
        rows=output_rows,
        manifest=FeatureManifest(
            schema_version=SCHEMA_VERSION,
            feature_set_version=config.feature_set_version,
            generator_name=GENERATOR_NAME,
            row_count=len(output_rows),
            features=_feature_specs(
                config.rolling_window,
                bool(higher_rows),
                config.higher_timeframes,
                bool(funding_rows),
            ),
        ),
    )


def _build_feature_row(
    rows: Sequence[dict[str, object]],
    index: int,
    config: FeatureConfig,
    higher_rows: Sequence[dict[str, object]],
) -> dict[str, object]:
    row = rows[index]
    close_time = _as_datetime(row["close_time"])
    source_available_at = _as_datetime(row["source_available_at"])
    window_rows = _window(rows, index, config.rolling_window)
    previous_row = rows[index - 1] if index >= 1 else None
    two_back_row = rows[index - 2] if index >= 2 else None

    rolling_high = max(_as_float(item["high"]) for item in window_rows)
    rolling_low = min(_as_float(item["low"]) for item in window_rows)
    close = _as_float(row["close"])
    open_price = _as_float(row["open"])
    high = _as_float(row["high"])
    low = _as_float(row["low"])
    volume_values = [_as_float(item["volume"]) for item in window_rows]
    taker_flow_values = [_taker_flow_imbalance(item) for item in window_rows]
    taker_buy_base_ratio_values = [_taker_buy_base_ratio(item) for item in window_rows]
    trade_count_values = [_optional_float(item.get("number_of_trades")) for item in window_rows]
    close_values = [_as_float(item["close"]) for item in window_rows]
    range_value = high - low
    rolling_range = rolling_high - rolling_low
    current_taker_flow = _taker_flow_imbalance(row)
    current_taker_buy_base_ratio = _taker_buy_base_ratio(row)
    current_trade_count = _optional_float(row.get("number_of_trades"))

    ma_name = f"ma_{config.rolling_window}"
    ma_slope_name = f"ma_slope_{config.rolling_window}"
    trend_above_ma_name = f"trend_above_ma_{config.rolling_window}"
    ma_slope_sign_name = f"ma_slope_sign_{config.rolling_window}"
    range_position_name = f"range_position_{config.rolling_window}"
    volume_zscore_name = f"volume_zscore_{config.rolling_window}"
    relative_volume_name = f"relative_volume_{config.rolling_window}"
    taker_flow_zscore_name = f"taker_flow_imbalance_zscore_{config.rolling_window}"
    taker_buy_base_ratio_mean_name = f"taker_buy_base_ratio_mean_{config.rolling_window}"
    trade_count_zscore_name = f"trade_count_zscore_{config.rolling_window}"
    volatility_expansion_name = f"volatility_expansion_{config.rolling_window}"
    volatility_bucket_name = f"volatility_bucket_{config.rolling_window}"
    realized_volatility_name = f"realized_volatility_{config.rolling_window}"
    ema_name = f"ema_{config.rolling_window}"
    rsi_name = f"rsi_{config.rolling_window}"
    stochastic_k_name = f"stochastic_k_{config.rolling_window}"
    atr_name = f"atr_{config.rolling_window}"
    normalized_atr_name = f"normalized_atr_{config.rolling_window}"
    bollinger_position_name = f"bollinger_position_{config.rolling_window}"
    bollinger_width_name = f"bollinger_width_{config.rolling_window}"
    macd_name = f"macd_{config.rolling_window}"
    macd_signal_name = f"macd_signal_{config.rolling_window}"
    macd_histogram_name = f"macd_histogram_{config.rolling_window}"
    dmi_plus_name = f"dmi_plus_{config.rolling_window}"
    dmi_minus_name = f"dmi_minus_{config.rolling_window}"
    adx_name = f"adx_{config.rolling_window}"

    current_ma = _mean(close_values) if len(window_rows) == config.rolling_window else None
    previous_ma = _previous_ma(rows, index, config.rolling_window)
    ma_slope = (
        _return(current_ma, previous_ma)
        if current_ma is not None and previous_ma is not None
        else None
    )
    volatility_expansion = (
        _volatility_expansion(window_rows) if len(window_rows) == config.rolling_window else None
    )
    true_range_values = _true_ranges(rows, index, config.rolling_window)
    atr = _mean(true_range_values) if len(true_range_values) == config.rolling_window else None
    dmi_plus, dmi_minus, adx = _dmi(rows, index, config.rolling_window)
    macd, macd_signal, macd_histogram = _macd(rows, index, config.rolling_window)
    realized_volatility = _realized_volatility(close_values)
    htf_current, htf_previous = _aligned_higher_timeframe_rows(higher_rows, close_time)

    feature_row: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "feature_set_version": config.feature_set_version,
        "venue": row["venue"],
        "market_type": row["market_type"],
        "symbol": row["symbol"],
        "timeframe": row["timeframe"],
        "decision_time": close_time,
        "source_window_start": _as_datetime(window_rows[0]["close_time"]),
        "source_window_end": close_time,
        "source_available_at": source_available_at,
        "warmup_missing_bars": max(config.rolling_window - len(window_rows), 0),
        "return_1": _return(close, _as_float(previous_row["close"])) if previous_row else None,
        "roc_2": _return(close, _as_float(two_back_row["close"])) if two_back_row else None,
        ma_name: current_ma,
        ma_slope_name: ma_slope,
        trend_above_ma_name: _flag(close >= current_ma) if current_ma is not None else None,
        ma_slope_sign_name: _sign(ma_slope),
        "close_location": _ratio(close - low, range_value),
        "candle_body_pct": _ratio(abs(close - open_price), range_value),
        "upper_wick_ratio": _ratio(high - max(open_price, close), range_value),
        "lower_wick_ratio": _ratio(min(open_price, close) - low, range_value),
        range_position_name: _ratio(close - rolling_low, rolling_range)
        if len(window_rows) == config.rolling_window
        else None,
        volume_zscore_name: _zscore(volume_values[-1], volume_values)
        if len(window_rows) == config.rolling_window
        else None,
        relative_volume_name: _ratio(volume_values[-1], _mean(volume_values))
        if len(window_rows) == config.rolling_window
        else None,
        "taker_buy_base_ratio": current_taker_buy_base_ratio,
        "taker_buy_quote_ratio": _taker_buy_quote_ratio(row),
        "taker_flow_imbalance": current_taker_flow,
        taker_flow_zscore_name: _zscore_optional(
            current_taker_flow,
            taker_flow_values,
            config.rolling_window,
        ),
        taker_buy_base_ratio_mean_name: _mean_optional(
            taker_buy_base_ratio_values,
            config.rolling_window,
        ),
        trade_count_zscore_name: _zscore_optional(
            current_trade_count,
            trade_count_values,
            config.rolling_window,
        ),
        volatility_expansion_name: volatility_expansion,
        volatility_bucket_name: _volatility_bucket(volatility_expansion),
        realized_volatility_name: realized_volatility
        if len(window_rows) == config.rolling_window
        else None,
        ema_name: _ema(close_values) if len(window_rows) == config.rolling_window else None,
        rsi_name: _rsi(close_values) if len(window_rows) == config.rolling_window else None,
        stochastic_k_name: _ratio(close - rolling_low, rolling_range)
        if len(window_rows) == config.rolling_window
        else None,
        atr_name: atr,
        normalized_atr_name: _ratio(atr, close) if atr is not None else None,
        bollinger_position_name: _bollinger_position(close_values)
        if len(window_rows) == config.rolling_window
        else None,
        bollinger_width_name: _bollinger_width(close_values)
        if len(window_rows) == config.rolling_window
        else None,
        macd_name: macd,
        macd_signal_name: macd_signal,
        macd_histogram_name: macd_histogram,
        dmi_plus_name: dmi_plus,
        dmi_minus_name: dmi_minus,
        adx_name: adx,
        "distance_from_rolling_high": _return(close, rolling_high),
        "distance_from_rolling_low": _return(close, rolling_low),
        "body_pressure": _body_pressure(open_price, close, range_value),
        "wick_pressure": _ratio(
            min(open_price, close) - low - (high - max(open_price, close)),
            range_value,
        ),
        "consecutive_bull_bars": float(_consecutive_bars(rows, index, bullish=True)),
        "consecutive_bear_bars": float(_consecutive_bars(rows, index, bullish=False)),
    }

    if htf_current is not None:
        htf_close = _as_float(htf_current["close"])
        feature_row["htf_close"] = htf_close
        feature_row["htf_return_1"] = (
            _return(htf_close, _as_float(htf_previous["close"])) if htf_previous else None
        )
    elif higher_rows:
        feature_row["htf_close"] = None
        feature_row["htf_return_1"] = None

    return feature_row


def _feature_specs(
    rolling_window: int,
    has_higher_timeframe: bool,
    higher_timeframes: tuple[str, ...],
    has_funding_rates: bool,
) -> tuple[FeatureSpec, ...]:
    specs = [
        FeatureSpec("return_1", "indicator", 2, "post_close", "One-bar close-to-close return."),
        FeatureSpec("roc_2", "indicator", 3, "post_close", "Two-bar rate of change."),
        FeatureSpec(
            f"ma_{rolling_window}",
            "regime",
            rolling_window,
            "post_close",
            "Rolling mean close price.",
        ),
        FeatureSpec(
            f"ma_slope_{rolling_window}",
            "regime",
            rolling_window + 1,
            "post_close",
            "Rolling mean close-price slope.",
        ),
        FeatureSpec(
            f"trend_above_ma_{rolling_window}",
            "regime",
            rolling_window,
            "post_close",
            "Numeric flag: 1 when close is at or above rolling mean, otherwise 0.",
        ),
        FeatureSpec(
            f"ma_slope_sign_{rolling_window}",
            "regime",
            rolling_window + 1,
            "post_close",
            "Numeric trend slope sign: -1, 0, or 1 from rolling mean slope.",
        ),
        FeatureSpec(
            f"range_position_{rolling_window}",
            "price_action",
            rolling_window,
            "post_close",
            "Close location inside rolling high-low range.",
        ),
        FeatureSpec(
            f"volume_zscore_{rolling_window}",
            "participation",
            rolling_window,
            "post_close",
            "Current volume z-score inside rolling window.",
        ),
        FeatureSpec(
            f"relative_volume_{rolling_window}",
            "participation",
            rolling_window,
            "post_close",
            "Current volume divided by rolling average volume.",
        ),
        FeatureSpec(
            "taker_buy_base_ratio",
            "microstructure",
            1,
            "post_close",
            "Taker buy base volume divided by total base volume.",
        ),
        FeatureSpec(
            "taker_buy_quote_ratio",
            "microstructure",
            1,
            "post_close",
            "Taker buy quote volume divided by total quote volume.",
        ),
        FeatureSpec(
            "taker_flow_imbalance",
            "microstructure",
            1,
            "post_close",
            "Aggressive taker buy minus sell base volume, normalized by total base volume.",
        ),
        FeatureSpec(
            f"taker_flow_imbalance_zscore_{rolling_window}",
            "microstructure",
            rolling_window,
            "post_close",
            "Current taker-flow imbalance z-score inside the rolling window.",
        ),
        FeatureSpec(
            f"taker_buy_base_ratio_mean_{rolling_window}",
            "microstructure",
            rolling_window,
            "post_close",
            "Rolling mean of taker buy base-volume share.",
        ),
        FeatureSpec(
            f"trade_count_zscore_{rolling_window}",
            "microstructure",
            rolling_window,
            "post_close",
            "Current number-of-trades z-score inside the rolling window.",
        ),
        FeatureSpec(
            f"volatility_expansion_{rolling_window}",
            "regime",
            rolling_window,
            "post_close",
            "Current candle range divided by average rolling range.",
        ),
        FeatureSpec(
            f"volatility_bucket_{rolling_window}",
            "regime",
            rolling_window,
            "post_close",
            "Numeric volatility regime bucket: 0 compressed, 1 normal, 2 expanded, 3 disorderly.",
        ),
        FeatureSpec(
            f"realized_volatility_{rolling_window}",
            "volatility",
            rolling_window,
            "post_close",
            "Standard deviation of close-to-close returns inside the rolling window.",
        ),
        FeatureSpec(
            f"ema_{rolling_window}",
            "trend",
            rolling_window,
            "post_close",
            "Exponential moving average over the rolling close window.",
        ),
        FeatureSpec(
            f"rsi_{rolling_window}",
            "momentum",
            rolling_window,
            "post_close",
            "RSI-style normalized momentum from gains and losses inside the rolling window.",
        ),
        FeatureSpec(
            f"stochastic_k_{rolling_window}",
            "momentum",
            rolling_window,
            "post_close",
            "Close location inside the rolling high-low range, normalized from 0 to 1.",
        ),
        FeatureSpec(
            f"atr_{rolling_window}",
            "volatility",
            rolling_window,
            "post_close",
            "Average true range over the rolling window.",
        ),
        FeatureSpec(
            f"normalized_atr_{rolling_window}",
            "volatility",
            rolling_window,
            "post_close",
            "Average true range divided by close.",
        ),
        FeatureSpec(
            f"bollinger_position_{rolling_window}",
            "volatility",
            rolling_window,
            "post_close",
            "Close position between two-standard-deviation Bollinger bands.",
        ),
        FeatureSpec(
            f"bollinger_width_{rolling_window}",
            "volatility",
            rolling_window,
            "post_close",
            "Two-standard-deviation Bollinger band width divided by rolling mean close.",
        ),
        FeatureSpec(
            f"macd_{rolling_window}",
            "trend",
            rolling_window,
            "post_close",
            "Fast EMA minus slow EMA using rolling-window-derived MACD spans.",
        ),
        FeatureSpec(
            f"macd_signal_{rolling_window}",
            "trend",
            rolling_window,
            "post_close",
            "EMA signal line of recent MACD values.",
        ),
        FeatureSpec(
            f"macd_histogram_{rolling_window}",
            "momentum",
            rolling_window,
            "post_close",
            "MACD minus MACD signal.",
        ),
        FeatureSpec(
            f"dmi_plus_{rolling_window}",
            "trend",
            rolling_window,
            "post_close",
            "Positive directional movement index over the rolling window.",
        ),
        FeatureSpec(
            f"dmi_minus_{rolling_window}",
            "trend",
            rolling_window,
            "post_close",
            "Negative directional movement index over the rolling window.",
        ),
        FeatureSpec(
            f"adx_{rolling_window}",
            "trend",
            rolling_window,
            "post_close",
            "Directional movement strength proxy over the rolling window.",
        ),
        FeatureSpec(
            "close_location",
            "price_action",
            1,
            "post_close",
            "Close inside candle range.",
        ),
        FeatureSpec(
            "candle_body_pct",
            "price_action",
            1,
            "post_close",
            "Body size vs candle range.",
        ),
        FeatureSpec("upper_wick_ratio", "price_action", 1, "post_close", "Upper wick vs range."),
        FeatureSpec("lower_wick_ratio", "price_action", 1, "post_close", "Lower wick vs range."),
        FeatureSpec(
            "body_pressure",
            "price_action",
            1,
            "post_close",
            "Signed candle body pressure: bullish body positive, bearish body negative.",
        ),
        FeatureSpec(
            "wick_pressure",
            "price_action",
            1,
            "post_close",
            "Lower wick pressure minus upper wick pressure, normalized by candle range.",
        ),
        FeatureSpec(
            "consecutive_bull_bars",
            "price_action",
            1,
            "post_close",
            "Count of consecutive bullish candles ending at the decision row.",
        ),
        FeatureSpec(
            "consecutive_bear_bars",
            "price_action",
            1,
            "post_close",
            "Count of consecutive bearish candles ending at the decision row.",
        ),
        FeatureSpec(
            "distance_from_rolling_high",
            "price_action",
            rolling_window,
            "post_close",
            "Close distance from rolling high.",
        ),
        FeatureSpec(
            "distance_from_rolling_low",
            "price_action",
            rolling_window,
            "post_close",
            "Close distance from rolling low.",
        ),
    ]
    if has_higher_timeframe:
        specs.extend(
            [
                FeatureSpec(
                    "htf_close",
                    "multi_timeframe",
                    1,
                    "post_close",
                    "Most recent higher-timeframe close available by decision time.",
                ),
                FeatureSpec(
                    "htf_return_1",
                    "multi_timeframe",
                    2,
                    "post_close",
                    "Higher-timeframe close-to-close return without future candle leakage.",
                ),
            ]
        )
    for timeframe in higher_timeframes:
        prefix = _multi_timeframe_prefix(timeframe)
        specs.extend(
            [
                FeatureSpec(
                    f"{prefix}_return_1",
                    "multi_timeframe",
                    2,
                    "post_close",
                    f"{timeframe} close-to-close return from derived closed candles.",
                ),
                FeatureSpec(
                    f"{prefix}_trend_above_ma_{rolling_window}",
                    "multi_timeframe",
                    rolling_window,
                    "post_close",
                    f"{timeframe} trend-above-MA flag from derived closed candles.",
                ),
                FeatureSpec(
                    f"{prefix}_ma_slope_sign_{rolling_window}",
                    "multi_timeframe",
                    rolling_window + 1,
                    "post_close",
                    f"{timeframe} rolling-MA slope sign from derived closed candles.",
                ),
                FeatureSpec(
                    f"{prefix}_range_position_{rolling_window}",
                    "multi_timeframe",
                    rolling_window,
                    "post_close",
                    f"{timeframe} close position inside rolling high-low range.",
                ),
                FeatureSpec(
                    f"{prefix}_volatility_bucket_{rolling_window}",
                    "multi_timeframe",
                    rolling_window,
                    "post_close",
                    f"{timeframe} volatility bucket from derived closed candles.",
                ),
                FeatureSpec(
                    f"{prefix}_market_positive_return_fraction",
                    "multi_timeframe_context",
                    2,
                    "post_close",
                    f"Fraction of symbols with positive {timeframe} return.",
                ),
                FeatureSpec(
                    f"{prefix}_risk_on_score_{rolling_window}",
                    "multi_timeframe_context",
                    rolling_window,
                    "post_close",
                    f"{timeframe} risk-on score from breadth and BTC/ETH trend flags.",
                ),
            ]
        )
        for reference in ("btc", "eth"):
            specs.extend(
                [
                    FeatureSpec(
                        f"{prefix}_{reference}_return_1",
                        "multi_timeframe_context",
                        2,
                        "post_close",
                        f"{reference.upper()} {timeframe} return.",
                    ),
                    FeatureSpec(
                        f"{prefix}_{reference}_trend_above_ma_{rolling_window}",
                        "multi_timeframe_context",
                        rolling_window,
                        "post_close",
                        f"{reference.upper()} {timeframe} trend-above-MA flag.",
                    ),
                    FeatureSpec(
                        f"{prefix}_{reference}_volatility_bucket_{rolling_window}",
                        "multi_timeframe_context",
                        rolling_window,
                        "post_close",
                        f"{reference.upper()} {timeframe} volatility bucket.",
                    ),
                ]
            )
    if has_funding_rates:
        specs.extend(_funding_feature_specs(rolling_window))
    specs.extend(_market_context_specs(rolling_window, has_funding_rates))
    return tuple(specs)


def _funding_feature_specs(rolling_window: int) -> list[FeatureSpec]:
    return [
        FeatureSpec(
            "funding_rate",
            "funding",
            1,
            "post_funding_time",
            "Most recent funding rate available by decision time.",
        ),
        FeatureSpec(
            f"funding_rate_mean_{rolling_window}",
            "funding",
            rolling_window,
            "post_funding_time",
            "Rolling mean of available funding rates.",
        ),
        FeatureSpec(
            f"funding_rate_zscore_{rolling_window}",
            "funding",
            rolling_window,
            "post_funding_time",
            "Current funding-rate z-score over recent funding events.",
        ),
        FeatureSpec(
            f"funding_rate_abs_zscore_{rolling_window}",
            "funding",
            rolling_window,
            "post_funding_time",
            "Absolute current funding-rate z-score over recent funding events.",
        ),
        FeatureSpec(
            "funding_rate_positive",
            "funding",
            1,
            "post_funding_time",
            "Flag set when the latest funding rate is positive.",
        ),
        FeatureSpec(
            "funding_rate_abs",
            "funding",
            1,
            "post_funding_time",
            "Absolute value of the latest funding rate.",
        ),
        FeatureSpec(
            "hours_since_funding",
            "funding",
            1,
            "post_funding_time",
            "Hours since the latest available funding event.",
        ),
        FeatureSpec(
            "hours_to_next_funding_estimate",
            "funding",
            1,
            "post_funding_time",
            "Eight-hour-cycle estimate of hours until the next funding event.",
        ),
    ]


def _market_context_specs(
    rolling_window: int,
    has_funding_rates: bool,
) -> list[FeatureSpec]:
    specs = [
        FeatureSpec(
            "market_positive_return_fraction",
            "market_context",
            2,
            "post_close",
            "Fraction of same-market symbols with positive one-bar return.",
        ),
        FeatureSpec(
            "market_average_return_1",
            "market_context",
            2,
            "post_close",
            "Average same-market one-bar return across available symbols.",
        ),
        FeatureSpec(
            f"market_above_ma_fraction_{rolling_window}",
            "market_context",
            rolling_window,
            "post_close",
            "Fraction of same-market symbols above their rolling mean.",
        ),
        FeatureSpec(
            f"risk_on_score_{rolling_window}",
            "market_context",
            rolling_window,
            "post_close",
            "Composite point-in-time risk-on score from breadth and BTC/ETH trend flags.",
        ),
        FeatureSpec(
            "market_taker_flow_imbalance",
            "market_context",
            1,
            "post_close",
            "Average same-market taker-flow imbalance across available symbols.",
        ),
    ]
    for reference in ("btc", "eth"):
        specs.extend(
            [
                FeatureSpec(
                    f"{reference}_return_1",
                    "market_context",
                    2,
                    "post_close",
                    f"{reference.upper()} one-bar return at the decision timestamp.",
                ),
                FeatureSpec(
                    f"{reference}_trend_above_ma_{rolling_window}",
                    "market_context",
                    rolling_window,
                    "post_close",
                    f"{reference.upper()} trend-above-MA flag at the decision timestamp.",
                ),
                FeatureSpec(
                    f"{reference}_volatility_bucket_{rolling_window}",
                    "market_context",
                    rolling_window,
                    "post_close",
                    f"{reference.upper()} volatility bucket at the decision timestamp.",
                ),
                FeatureSpec(
                    f"relative_strength_vs_{reference}_1",
                    "market_context",
                    2,
                    "post_close",
                    f"Symbol one-bar return minus {reference.upper()} one-bar return.",
                ),
                FeatureSpec(
                    f"correlation_to_{reference}_{rolling_window}",
                    "market_context",
                    rolling_window,
                    "post_close",
                    f"Rolling return correlation to {reference.upper()}.",
                ),
                FeatureSpec(
                    f"beta_to_{reference}_{rolling_window}",
                    "market_context",
                    rolling_window,
                    "post_close",
                    f"Rolling return beta to {reference.upper()}.",
                ),
                FeatureSpec(
                    f"{reference}_taker_flow_imbalance",
                    "market_context",
                    1,
                    "post_close",
                    f"{reference.upper()} taker-flow imbalance at the decision timestamp.",
                ),
                FeatureSpec(
                    f"relative_taker_flow_vs_{reference}",
                    "market_context",
                    1,
                    "post_close",
                    f"Symbol taker-flow imbalance minus {reference.upper()} taker-flow imbalance.",
                ),
            ]
        )
    if has_funding_rates:
        specs.extend(
            [
                FeatureSpec(
                    "market_average_funding_rate",
                    "funding_context",
                    1,
                    "post_funding_time",
                    "Average latest funding rate across same-market symbols.",
                ),
                FeatureSpec(
                    "market_positive_funding_fraction",
                    "funding_context",
                    1,
                    "post_funding_time",
                    "Fraction of same-market symbols with positive latest funding.",
                ),
            ]
        )
        for reference in ("btc", "eth"):
            specs.extend(
                [
                    FeatureSpec(
                        f"{reference}_funding_rate",
                        "funding_context",
                        1,
                        "post_funding_time",
                        f"{reference.upper()} latest funding rate at the decision timestamp.",
                    ),
                    FeatureSpec(
                        f"relative_funding_vs_{reference}",
                        "funding_context",
                        1,
                        "post_funding_time",
                        f"Symbol latest funding rate minus {reference.upper()} latest funding.",
                    ),
                ]
            )
    return specs


def _window(
    rows: Sequence[dict[str, object]],
    index: int,
    size: int,
) -> Sequence[dict[str, object]]:
    start = max(index - size + 1, 0)
    return rows[start : index + 1]


def _add_market_context_features(rows: list[dict[str, object]], rolling_window: int) -> None:
    by_context: dict[tuple[object, ...], list[dict[str, object]]] = {}
    by_series: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in rows:
        context_key = (
            row["venue"],
            row["market_type"],
            row["timeframe"],
            row["decision_time"],
        )
        series_key = (
            row["venue"],
            row["market_type"],
            row["timeframe"],
            row["symbol"],
        )
        by_context.setdefault(context_key, []).append(row)
        by_series.setdefault(series_key, []).append(row)

    for series_rows in by_series.values():
        series_rows.sort(key=lambda row: row["decision_time"])

    trend_name = f"trend_above_ma_{rolling_window}"
    volatility_bucket_name = f"volatility_bucket_{rolling_window}"
    market_above_ma_name = f"market_above_ma_fraction_{rolling_window}"
    risk_on_name = f"risk_on_score_{rolling_window}"

    for context_rows in by_context.values():
        reference_rows = {
            str(row["symbol"]).upper(): row
            for row in context_rows
            if str(row["symbol"]).upper() in REFERENCE_SYMBOLS
        }
        numeric_returns = [_number(row.get("return_1")) for row in context_rows]
        numeric_returns = [value for value in numeric_returns if value is not None]
        trend_flags = [_number(row.get(trend_name)) for row in context_rows]
        trend_flags = [value for value in trend_flags if value is not None]
        taker_flows = [_number(row.get("taker_flow_imbalance")) for row in context_rows]
        taker_flows = [value for value in taker_flows if value is not None]
        funding_rates = [_number(row.get("funding_rate")) for row in context_rows]
        funding_rates = [value for value in funding_rates if value is not None]
        market_positive_fraction = (
            sum(1 for value in numeric_returns if value > 0) / len(numeric_returns)
            if numeric_returns
            else None
        )
        market_average_return = _mean(numeric_returns) if numeric_returns else None
        market_above_ma_fraction = _mean(trend_flags) if trend_flags else None
        market_taker_flow_imbalance = _mean(taker_flows) if taker_flows else None
        market_average_funding_rate = _mean(funding_rates) if funding_rates else None
        market_positive_funding_fraction = (
            sum(1 for value in funding_rates if value > 0) / len(funding_rates)
            if funding_rates
            else None
        )

        reference_trend_flags = [
            _number(reference_rows[symbol].get(trend_name))
            for symbol in REFERENCE_SYMBOLS
            if symbol in reference_rows
        ]
        breadth_inputs = [
            market_positive_fraction,
            market_above_ma_fraction,
            *reference_trend_flags,
        ]
        risk_inputs = [value for value in breadth_inputs if value is not None]
        risk_on_score = _mean(risk_inputs) if risk_inputs else None

        for row in context_rows:
            row["market_positive_return_fraction"] = market_positive_fraction
            row["market_average_return_1"] = market_average_return
            row[market_above_ma_name] = market_above_ma_fraction
            row[risk_on_name] = risk_on_score
            row["market_taker_flow_imbalance"] = market_taker_flow_imbalance
            if "funding_rate" in row:
                row["market_average_funding_rate"] = market_average_funding_rate
                row["market_positive_funding_fraction"] = market_positive_funding_fraction
            for symbol, prefix in (("BTCUSDT", "btc"), ("ETHUSDT", "eth")):
                reference_row = reference_rows.get(symbol)
                reference_return = (
                    _number(reference_row.get("return_1")) if reference_row is not None else None
                )
                reference_taker_flow = (
                    _number(reference_row.get("taker_flow_imbalance"))
                    if reference_row is not None
                    else None
                )
                reference_funding_rate = (
                    _number(reference_row.get("funding_rate"))
                    if reference_row is not None
                    else None
                )
                row[f"{prefix}_return_1"] = reference_return
                row[f"{prefix}_trend_above_ma_{rolling_window}"] = (
                    _number(reference_row.get(trend_name)) if reference_row is not None else None
                )
                row[f"{prefix}_volatility_bucket_{rolling_window}"] = (
                    _number(reference_row.get(volatility_bucket_name))
                    if reference_row is not None
                    else None
                )
                row[f"relative_strength_vs_{prefix}_1"] = _difference(
                    _number(row.get("return_1")),
                    reference_return,
                )
                row[f"{prefix}_taker_flow_imbalance"] = reference_taker_flow
                row[f"relative_taker_flow_vs_{prefix}"] = _difference(
                    _number(row.get("taker_flow_imbalance")),
                    reference_taker_flow,
                )
                if "funding_rate" in row:
                    row[f"{prefix}_funding_rate"] = reference_funding_rate
                    row[f"relative_funding_vs_{prefix}"] = _difference(
                        _number(row.get("funding_rate")),
                        reference_funding_rate,
                    )

    for series_key, series_rows in by_series.items():
        venue, market_type, timeframe, _symbol = series_key
        row_index = {id(row): index for index, row in enumerate(series_rows)}
        for reference_symbol, prefix in (("BTCUSDT", "btc"), ("ETHUSDT", "eth")):
            reference_rows = by_series.get((venue, market_type, timeframe, reference_symbol), [])
            reference_by_time = {row["decision_time"]: row for row in reference_rows}
            for row in series_rows:
                candidate_index = row_index[id(row)]
                candidate_returns, reference_returns = _aligned_return_windows(
                    series_rows,
                    candidate_index,
                    reference_by_time,
                    rolling_window,
                )
                row[f"correlation_to_{prefix}_{rolling_window}"] = _correlation(
                    candidate_returns,
                    reference_returns,
                )
                row[f"beta_to_{prefix}_{rolling_window}"] = _beta(
                    candidate_returns,
                    reference_returns,
                )


def _add_derived_multi_timeframe_features(
    feature_rows: list[dict[str, object]],
    source_rows: Sequence[dict[str, object]],
    config: FeatureConfig,
) -> None:
    for timeframe in config.higher_timeframes:
        frame_minutes = _timeframe_minutes(timeframe)
        prefix = _multi_timeframe_prefix(timeframe)
        names = _multi_timeframe_feature_names(prefix, config.rolling_window)
        htf_rows = _aggregate_closed_timeframe_rows(source_rows, timeframe, frame_minutes)
        htf_features = _multi_timeframe_feature_rows(htf_rows, config.rolling_window, prefix)
        pointer = -1
        for row in feature_rows:
            decision_time = _as_datetime(row["decision_time"])
            while (
                pointer + 1 < len(htf_features)
                and _as_datetime(htf_features[pointer + 1]["decision_time"]) <= decision_time
            ):
                pointer += 1
            if pointer < 0:
                for name in names:
                    row[name] = None
                continue
            htf_feature = htf_features[pointer]
            for name in names:
                row[name] = htf_feature.get(name)


def _add_funding_features(
    feature_rows: list[dict[str, object]],
    funding_rows: Sequence[dict[str, object]],
    rolling_window: int,
) -> None:
    if not funding_rows:
        return
    if not feature_rows:
        return
    group_key = _base_group_key(feature_rows[0])
    group_funding_rows = [row for row in funding_rows if _funding_group_key(row) == group_key]
    names = _funding_feature_names(rolling_window)
    pointer = -1
    for row in feature_rows:
        decision_time = _as_datetime(row["decision_time"])
        while (
            pointer + 1 < len(group_funding_rows)
            and _as_datetime(group_funding_rows[pointer + 1]["funding_time"]) <= decision_time
            and _as_datetime(group_funding_rows[pointer + 1]["source_available_at"])
            <= decision_time
        ):
            pointer += 1
        if pointer < 0:
            for name in names:
                row[name] = None
            continue
        latest = group_funding_rows[pointer]
        window_rows = group_funding_rows[max(pointer - rolling_window + 1, 0) : pointer + 1]
        funding_rate = _number(latest.get("funding_rate"))
        funding_values = [_number(item.get("funding_rate")) for item in window_rows]
        funding_zscore = _zscore_optional(funding_rate, funding_values, rolling_window)
        funding_time = _as_datetime(latest["funding_time"])
        hours_since_funding = (decision_time - funding_time).total_seconds() / 3600
        row.update(
            {
                "funding_rate": funding_rate,
                f"funding_rate_mean_{rolling_window}": _mean_optional(
                    funding_values,
                    rolling_window,
                ),
                f"funding_rate_zscore_{rolling_window}": funding_zscore,
                f"funding_rate_abs_zscore_{rolling_window}": abs(funding_zscore)
                if funding_zscore is not None
                else None,
                "funding_rate_positive": _flag(funding_rate > 0)
                if funding_rate is not None
                else None,
                "funding_rate_abs": abs(funding_rate) if funding_rate is not None else None,
                "hours_since_funding": hours_since_funding,
                "hours_to_next_funding_estimate": max(8 - hours_since_funding, 0.0),
            }
        )


def _funding_feature_names(rolling_window: int) -> tuple[str, ...]:
    return (
        "funding_rate",
        f"funding_rate_mean_{rolling_window}",
        f"funding_rate_zscore_{rolling_window}",
        f"funding_rate_abs_zscore_{rolling_window}",
        "funding_rate_positive",
        "funding_rate_abs",
        "hours_since_funding",
        "hours_to_next_funding_estimate",
    )


def _aggregate_closed_timeframe_rows(
    rows: Sequence[dict[str, object]],
    timeframe: str,
    frame_minutes: int,
) -> list[dict[str, object]]:
    aggregated: list[dict[str, object]] = []
    current_rows: list[dict[str, object]] = []
    for row in rows:
        current_rows.append(row)
        close_time = _as_datetime(row["close_time"])
        if _total_minutes(close_time) % frame_minutes != 0:
            continue
        first = current_rows[0]
        last = current_rows[-1]
        aggregated.append(
            {
                "schema_version": SCHEMA_VERSION,
                "venue": first["venue"],
                "market_type": first["market_type"],
                "symbol": first["symbol"],
                "base_asset": first.get("base_asset"),
                "quote_asset": first.get("quote_asset"),
                "timeframe": timeframe,
                "open_time": first["open_time"],
                "close_time": last["close_time"],
                "source_available_at": last["source_available_at"],
                "open": first["open"],
                "high": max(_as_float(item["high"]) for item in current_rows),
                "low": min(_as_float(item["low"]) for item in current_rows),
                "close": last["close"],
                "volume": sum(_as_float(item["volume"]) for item in current_rows),
            }
        )
        current_rows = []
    return aggregated


def _multi_timeframe_feature_rows(
    rows: Sequence[dict[str, object]],
    rolling_window: int,
    prefix: str,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        window_rows = _window(rows, index, rolling_window)
        close = _as_float(row["close"])
        previous_row = rows[index - 1] if index >= 1 else None
        close_values = [_as_float(item["close"]) for item in window_rows]
        rolling_high = max(_as_float(item["high"]) for item in window_rows)
        rolling_low = min(_as_float(item["low"]) for item in window_rows)
        rolling_range = rolling_high - rolling_low
        current_ma = _mean(close_values) if len(window_rows) == rolling_window else None
        previous_ma = _previous_ma(rows, index, rolling_window)
        ma_slope = (
            _return(current_ma, previous_ma)
            if current_ma is not None and previous_ma is not None
            else None
        )
        volatility_expansion = (
            _volatility_expansion(window_rows) if len(window_rows) == rolling_window else None
        )
        output.append(
            {
                "decision_time": _as_datetime(row["close_time"]),
                f"{prefix}_return_1": _return(close, _as_float(previous_row["close"]))
                if previous_row
                else None,
                f"{prefix}_trend_above_ma_{rolling_window}": _flag(close >= current_ma)
                if current_ma is not None
                else None,
                f"{prefix}_ma_slope_sign_{rolling_window}": _sign(ma_slope),
                f"{prefix}_range_position_{rolling_window}": _ratio(
                    close - rolling_low,
                    rolling_range,
                )
                if len(window_rows) == rolling_window
                else None,
                f"{prefix}_volatility_bucket_{rolling_window}": _volatility_bucket(
                    volatility_expansion
                ),
            }
        )
    return output


def _add_multi_timeframe_market_context_features(
    rows: list[dict[str, object]],
    config: FeatureConfig,
) -> None:
    if not config.higher_timeframes:
        return
    by_context: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in rows:
        context_key = (
            row["venue"],
            row["market_type"],
            row["timeframe"],
            row["decision_time"],
        )
        by_context.setdefault(context_key, []).append(row)

    for timeframe in config.higher_timeframes:
        prefix = _multi_timeframe_prefix(timeframe)
        return_name = f"{prefix}_return_1"
        trend_name = f"{prefix}_trend_above_ma_{config.rolling_window}"
        volatility_bucket_name = f"{prefix}_volatility_bucket_{config.rolling_window}"
        market_positive_name = f"{prefix}_market_positive_return_fraction"
        risk_on_name = f"{prefix}_risk_on_score_{config.rolling_window}"

        for context_rows in by_context.values():
            reference_rows = {
                str(row["symbol"]).upper(): row
                for row in context_rows
                if str(row["symbol"]).upper() in REFERENCE_SYMBOLS
            }
            returns = [_number(row.get(return_name)) for row in context_rows]
            returns = [value for value in returns if value is not None]
            trend_flags = [_number(row.get(trend_name)) for row in context_rows]
            trend_flags = [value for value in trend_flags if value is not None]
            market_positive_fraction = (
                sum(1 for value in returns if value > 0) / len(returns) if returns else None
            )
            market_above_ma_fraction = _mean(trend_flags) if trend_flags else None
            reference_trend_flags = [
                _number(reference_rows[symbol].get(trend_name))
                for symbol in REFERENCE_SYMBOLS
                if symbol in reference_rows
            ]
            risk_inputs = [
                value
                for value in [
                    market_positive_fraction,
                    market_above_ma_fraction,
                    *reference_trend_flags,
                ]
                if value is not None
            ]
            risk_on_score = _mean(risk_inputs) if risk_inputs else None

            for row in context_rows:
                row[market_positive_name] = market_positive_fraction
                row[risk_on_name] = risk_on_score
                for reference_symbol, reference_prefix in (("BTCUSDT", "btc"), ("ETHUSDT", "eth")):
                    reference_row = reference_rows.get(reference_symbol)
                    row[f"{prefix}_{reference_prefix}_return_1"] = _reference_number(
                        reference_row,
                        return_name,
                    )
                    row[f"{prefix}_{reference_prefix}_trend_above_ma_{config.rolling_window}"] = (
                        _reference_number(reference_row, trend_name)
                    )
                    row[
                        f"{prefix}_{reference_prefix}_volatility_bucket_{config.rolling_window}"
                    ] = (
                        _number(reference_row.get(volatility_bucket_name))
                        if reference_row is not None
                        else None
                    )


def _multi_timeframe_feature_names(prefix: str, rolling_window: int) -> tuple[str, ...]:
    return (
        f"{prefix}_return_1",
        f"{prefix}_trend_above_ma_{rolling_window}",
        f"{prefix}_ma_slope_sign_{rolling_window}",
        f"{prefix}_range_position_{rolling_window}",
        f"{prefix}_volatility_bucket_{rolling_window}",
    )


def _multi_timeframe_prefix(timeframe: str) -> str:
    return f"mtf_{timeframe.lower()}"


def _timeframe_minutes(timeframe: str) -> int:
    if not timeframe.endswith("m"):
        raise ValueError("derived higher timeframes must be minute-based")
    minutes = int(timeframe[:-1])
    if minutes <= 1:
        raise ValueError("derived higher timeframes must be greater than 1m")
    return minutes


def _total_minutes(value: datetime) -> int:
    return int(value.timestamp() // 60)


def _reference_number(row: dict[str, object] | None, name: str) -> float | None:
    return _number(row.get(name)) if row is not None else None


def _aligned_return_windows(
    series_rows: Sequence[dict[str, object]],
    index: int,
    reference_by_time: dict[object, dict[str, object]],
    size: int,
) -> tuple[list[float], list[float]]:
    start = max(index - size + 1, 0)
    candidate_returns: list[float] = []
    reference_returns: list[float] = []
    for row in series_rows[start : index + 1]:
        reference_row = reference_by_time.get(row["decision_time"])
        candidate_return = _number(row.get("return_1"))
        reference_return = _number(reference_row.get("return_1")) if reference_row else None
        if candidate_return is not None and reference_return is not None:
            candidate_returns.append(candidate_return)
            reference_returns.append(reference_return)
    return candidate_returns, reference_returns


def _previous_ma(rows: Sequence[dict[str, object]], index: int, size: int) -> float | None:
    if index < size:
        return None
    previous_window = rows[index - size : index]
    return _mean([_as_float(row["close"]) for row in previous_window])


def _aligned_higher_timeframe_rows(
    higher_rows: Sequence[dict[str, object]],
    decision_time: datetime,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    available = [
        row
        for row in higher_rows
        if _as_datetime(row["source_available_at"]) <= decision_time
        and _as_datetime(row["close_time"]) <= decision_time
    ]
    if not available:
        return None, None
    if len(available) == 1:
        return available[-1], None
    return available[-1], available[-2]


def _volatility_expansion(rows: Sequence[dict[str, object]]) -> float | None:
    ranges = [_as_float(row["high"]) - _as_float(row["low"]) for row in rows]
    average_range = _mean(ranges)
    return _ratio(ranges[-1], average_range)


def _true_ranges(
    rows: Sequence[dict[str, object]],
    index: int,
    size: int,
) -> list[float]:
    start = max(index - size + 1, 0)
    values: list[float] = []
    for current_index in range(start, index + 1):
        row = rows[current_index]
        high = _as_float(row["high"])
        low = _as_float(row["low"])
        previous_close = _as_float(rows[current_index - 1]["close"]) if current_index >= 1 else None
        if previous_close is None:
            values.append(high - low)
        else:
            values.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return values


def _realized_volatility(values: Sequence[float]) -> float | None:
    returns = [
        _return(current, previous) for previous, current in zip(values, values[1:], strict=False)
    ]
    numeric_returns = [value for value in returns if value is not None]
    if len(numeric_returns) < 2:
        return None
    return _standard_deviation(numeric_returns)


def _ema(values: Sequence[float]) -> float:
    alpha = 2 / (len(values) + 1)
    ema_value = values[0]
    for value in values[1:]:
        ema_value = value * alpha + ema_value * (1 - alpha)
    return ema_value


def _rsi(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values, values[1:], strict=False):
        change = current - previous
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))
    average_gain = _mean(gains)
    average_loss = _mean(losses)
    if average_gain == 0 and average_loss == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def _bollinger_position(values: Sequence[float]) -> float | None:
    mean_value = _mean(values)
    standard_deviation = _standard_deviation(values)
    upper_band = mean_value + 2 * standard_deviation
    lower_band = mean_value - 2 * standard_deviation
    return _ratio(values[-1] - lower_band, upper_band - lower_band)


def _bollinger_width(values: Sequence[float]) -> float | None:
    mean_value = _mean(values)
    standard_deviation = _standard_deviation(values)
    return _ratio(4 * standard_deviation, mean_value)


def _macd(
    rows: Sequence[dict[str, object]],
    index: int,
    slow_span: int,
) -> tuple[float | None, float | None, float | None]:
    fast_span = max(2, slow_span // 2)
    signal_span = max(2, slow_span // 3)
    if index + 1 < slow_span:
        return None, None, None

    macd_values: list[float] = []
    start_index = max(slow_span - 1, index - signal_span + 1)
    for end_index in range(start_index, index + 1):
        slow_values = [
            _as_float(row["close"]) for row in rows[end_index - slow_span + 1 : end_index + 1]
        ]
        fast_values = [
            _as_float(row["close"]) for row in rows[end_index - fast_span + 1 : end_index + 1]
        ]
        macd_values.append(_ema(fast_values) - _ema(slow_values))

    macd_value = macd_values[-1]
    if len(macd_values) < signal_span:
        return macd_value, None, None
    signal_value = _ema(macd_values[-signal_span:])
    return macd_value, signal_value, macd_value - signal_value


def _dmi(
    rows: Sequence[dict[str, object]],
    index: int,
    size: int,
) -> tuple[float | None, float | None, float | None]:
    if index + 1 < size or index == 0:
        return None, None, None
    start = max(index - size + 1, 1)
    plus_dm_values: list[float] = []
    minus_dm_values: list[float] = []
    true_range_values: list[float] = []
    for current_index in range(start, index + 1):
        current = rows[current_index]
        previous = rows[current_index - 1]
        high = _as_float(current["high"])
        low = _as_float(current["low"])
        previous_high = _as_float(previous["high"])
        previous_low = _as_float(previous["low"])
        previous_close = _as_float(previous["close"])
        up_move = high - previous_high
        down_move = previous_low - low
        plus_dm_values.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm_values.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        true_range_values.append(
            max(high - low, abs(high - previous_close), abs(low - previous_close))
        )

    true_range_sum = sum(true_range_values)
    if true_range_sum == 0:
        return None, None, None
    plus_di = 100 * sum(plus_dm_values) / true_range_sum
    minus_di = 100 * sum(minus_dm_values) / true_range_sum
    directional_sum = plus_di + minus_di
    adx = 0.0 if directional_sum == 0 else 100 * abs(plus_di - minus_di) / directional_sum
    return plus_di, minus_di, adx


def _body_pressure(open_price: float, close: float, range_value: float) -> float | None:
    body_ratio = _ratio(abs(close - open_price), range_value)
    if body_ratio is None:
        return None
    return body_ratio if close >= open_price else -body_ratio


def _consecutive_bars(
    rows: Sequence[dict[str, object]],
    index: int,
    *,
    bullish: bool,
) -> int:
    count = 0
    for current_index in range(index, -1, -1):
        row = rows[current_index]
        close = _as_float(row["close"])
        open_price = _as_float(row["open"])
        matches = close >= open_price if bullish else close < open_price
        if not matches:
            break
        count += 1
    return count


def _volatility_bucket(value: float | None) -> float | None:
    if value is None:
        return None
    if value < 0.75:
        return 0.0
    if value < 1.5:
        return 1.0
    if value < 2.5:
        return 2.0
    return 3.0


def _taker_buy_base_ratio(row: dict[str, object]) -> float | None:
    taker_buy_base = _optional_float(row.get("taker_buy_base_volume"))
    if taker_buy_base is None:
        return None
    return _ratio(taker_buy_base, _as_float(row["volume"]))


def _taker_buy_quote_ratio(row: dict[str, object]) -> float | None:
    taker_buy_quote = _optional_float(row.get("taker_buy_quote_volume"))
    quote_volume = _optional_float(row.get("quote_volume"))
    if taker_buy_quote is None or quote_volume is None:
        return None
    return _ratio(taker_buy_quote, quote_volume)


def _taker_flow_imbalance(row: dict[str, object]) -> float | None:
    ratio = _taker_buy_base_ratio(row)
    if ratio is None:
        return None
    return ratio * 2 - 1


def _mean_optional(values: Sequence[float | None], expected_count: int) -> float | None:
    numeric = _complete_numeric_values(values, expected_count)
    return _mean(numeric) if numeric is not None else None


def _zscore_optional(
    value: float | None,
    values: Sequence[float | None],
    expected_count: int,
) -> float | None:
    numeric = _complete_numeric_values(values, expected_count)
    if value is None or numeric is None:
        return None
    return _zscore(value, numeric)


def _complete_numeric_values(
    values: Sequence[float | None],
    expected_count: int,
) -> list[float] | None:
    if len(values) != expected_count:
        return None
    numeric = [value for value in values if value is not None]
    return numeric if len(numeric) == expected_count else None


def _flag(value: bool) -> float:
    return 1.0 if value else 0.0


def _sign(value: float | None) -> float | None:
    if value is None:
        return None
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return 0.0


def _return(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return current / previous - 1


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _zscore(value: float, values: Sequence[float]) -> float | None:
    mean_value = _mean(values)
    standard_deviation = _standard_deviation(values)
    if standard_deviation == 0:
        return None
    return (value - mean_value) / standard_deviation


def _standard_deviation(values: Sequence[float]) -> float:
    mean_value = _mean(values)
    variance = _mean([(item - mean_value) ** 2 for item in values])
    return math.sqrt(variance)


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_std = _standard_deviation(left)
    right_std = _standard_deviation(right)
    if left_std == 0 or right_std == 0:
        return None
    covariance = _covariance(left, right)
    return covariance / (left_std * right_std)


def _beta(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    right_variance = _standard_deviation(right) ** 2
    if right_variance == 0:
        return None
    return _covariance(left, right) / right_variance


def _covariance(left: Sequence[float], right: Sequence[float]) -> float:
    left_mean = _mean(left)
    right_mean = _mean(right)
    return _mean(
        [
            (left_value - left_mean) * (right_value - right_mean)
            for left_value, right_value in zip(left, right, strict=False)
        ]
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _optional_float(value: object) -> float | None:
    return _number(value)


def _sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        row["close_time"],
    )


def _funding_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["funding_time"],
    )


def _group_rows(rows: Sequence[dict[str, object]]) -> list[list[dict[str, object]]]:
    groups: list[list[dict[str, object]]] = []
    for row in rows:
        if not groups or _sort_group_key(groups[-1][0]) != _sort_group_key(row):
            groups.append([])
        groups[-1].append(row)
    return groups


def _sort_group_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
    )


def _base_group_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
    )


def _funding_group_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
    )


def _higher_timeframe_group_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
    )


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)!r}")
    return value


def _as_float(value: object) -> float:
    return float(value)
