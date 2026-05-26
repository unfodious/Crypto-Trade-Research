"""Point-in-time OHLCV feature engineering primitives."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

SCHEMA_VERSION = "research.dataset.v1"
GENERATOR_NAME = "crypto_trade_research.ohlcv_features"


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    feature_set_version: str
    rolling_window: int = 20


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
) -> FeatureFrame:
    """Generate deterministic, post-close OHLCV features from clean candle rows."""

    if config.rolling_window < 2:
        raise ValueError("rolling_window must be at least 2")
    if not rows:
        raise ValueError("rows must not be empty")

    sorted_rows = sorted(rows, key=_sort_key)
    higher_rows = sorted(higher_timeframe_rows or [], key=_sort_key)
    output_rows: list[dict[str, object]] = []
    for group_rows in _group_rows(sorted_rows):
        base_group_key = _base_group_key(group_rows[0])
        group_higher_rows = [
            row for row in higher_rows if _higher_timeframe_group_key(row) == base_group_key
        ]
        output_rows.extend(
            _build_feature_row(group_rows, index, config, group_higher_rows)
            for index in range(len(group_rows))
        )

    return FeatureFrame(
        rows=output_rows,
        manifest=FeatureManifest(
            schema_version=SCHEMA_VERSION,
            feature_set_version=config.feature_set_version,
            generator_name=GENERATOR_NAME,
            row_count=len(output_rows),
            features=_feature_specs(config.rolling_window, bool(higher_rows)),
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
    close_values = [_as_float(item["close"]) for item in window_rows]
    range_value = high - low
    rolling_range = rolling_high - rolling_low

    ma_name = f"ma_{config.rolling_window}"
    ma_slope_name = f"ma_slope_{config.rolling_window}"
    trend_above_ma_name = f"trend_above_ma_{config.rolling_window}"
    ma_slope_sign_name = f"ma_slope_sign_{config.rolling_window}"
    range_position_name = f"range_position_{config.rolling_window}"
    volume_zscore_name = f"volume_zscore_{config.rolling_window}"
    volatility_expansion_name = f"volatility_expansion_{config.rolling_window}"
    volatility_bucket_name = f"volatility_bucket_{config.rolling_window}"

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
        volatility_expansion_name: volatility_expansion,
        volatility_bucket_name: _volatility_bucket(volatility_expansion),
        "distance_from_rolling_high": _return(close, rolling_high),
        "distance_from_rolling_low": _return(close, rolling_low),
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


def _feature_specs(rolling_window: int, has_higher_timeframe: bool) -> tuple[FeatureSpec, ...]:
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
    return tuple(specs)


def _window(
    rows: Sequence[dict[str, object]],
    index: int,
    size: int,
) -> Sequence[dict[str, object]]:
    start = max(index - size + 1, 0)
    return rows[start : index + 1]


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


def _zscore(value: float, values: Sequence[float]) -> float | None:
    mean_value = _mean(values)
    variance = _mean([(item - mean_value) ** 2 for item in values])
    standard_deviation = math.sqrt(variance)
    if standard_deviation == 0:
        return None
    return (value - mean_value) / standard_deviation


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        row["close_time"],
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
