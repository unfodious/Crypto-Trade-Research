from datetime import UTC, datetime

import pytest

from crypto_trade_research.features.core import (
    FeatureConfig,
    generate_ohlcv_features,
)


def _ts(minute: int) -> datetime:
    return datetime(2026, 1, 1, 0, minute, tzinfo=UTC)


def _bar(
    minute: int,
    close: float,
    high: float | None = None,
    low: float | None = None,
    volume: float = 100.0,
    timeframe: str = "1m",
    symbol: str = "BTCUSDT",
) -> dict[str, object]:
    return {
        "schema_version": "research.dataset.v1",
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": symbol,
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "timeframe": timeframe,
        "open_time": _ts(minute - 1),
        "close_time": _ts(minute),
        "source_available_at": _ts(minute),
        "open": close - 1,
        "high": high if high is not None else close + 2,
        "low": low if low is not None else close - 2,
        "close": close,
        "volume": volume,
    }


def test_generate_ohlcv_features_is_deterministic_and_documents_columns() -> None:
    frame = generate_ohlcv_features(
        [
            _bar(1, close=100, volume=100),
            _bar(2, close=102, volume=120),
            _bar(3, close=101, volume=80),
            _bar(4, close=104, volume=140),
        ],
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=3),
    )

    assert frame.manifest.feature_set_version == "unit.features.v1"
    assert frame.manifest.row_count == 4
    feature_names = {spec.name for spec in frame.manifest.features}
    assert {
        "return_1",
        "roc_2",
        "ma_3",
        "ma_slope_3",
        "range_position_3",
        "volume_zscore_3",
        "candle_body_pct",
        "close_location",
    } <= feature_names
    assert all(spec.availability == "post_close" for spec in frame.manifest.features)

    first_row = frame.rows[0]
    assert first_row["return_1"] is None
    assert first_row["roc_2"] is None
    assert first_row["ma_3"] is None
    assert first_row["warmup_missing_bars"] == 2

    last_row = frame.rows[-1]
    assert last_row["decision_time"] == _ts(4)
    assert last_row["return_1"] == pytest.approx(0.0297029702970297)
    assert last_row["roc_2"] == pytest.approx(0.0196078431372549)
    assert last_row["ma_3"] == pytest.approx(102.33333333333333)
    assert last_row["range_position_3"] == pytest.approx(5 / 7)
    assert last_row["volume_zscore_3"] == pytest.approx(1.0690449676496976)


def test_feature_generation_sorts_rows_and_keeps_point_in_time_windows() -> None:
    frame = generate_ohlcv_features(
        [
            _bar(3, close=103),
            _bar(1, close=100),
            _bar(2, close=102),
        ],
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=2),
    )

    assert [row["decision_time"] for row in frame.rows] == [_ts(1), _ts(2), _ts(3)]
    assert frame.rows[-1]["source_window_start"] == _ts(2)
    assert frame.rows[-1]["source_window_end"] == _ts(3)
    assert frame.rows[-1]["ma_2"] == 102.5


def test_higher_timeframe_alignment_does_not_leak_future_candle_close() -> None:
    frame = generate_ohlcv_features(
        [
            _bar(1, close=100),
            _bar(2, close=101),
            _bar(3, close=102),
            _bar(4, close=103),
            _bar(5, close=104),
        ],
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=2),
        higher_timeframe_rows=[
            _bar(3, close=110, timeframe="3m"),
            _bar(6, close=90, timeframe="3m"),
        ],
    )

    aligned = [row["htf_close"] for row in frame.rows]
    assert aligned == [None, None, 110.0, 110.0, 110.0]
    assert frame.rows[-1]["htf_return_1"] is None


def test_feature_windows_do_not_cross_symbol_boundaries() -> None:
    frame = generate_ohlcv_features(
        [
            _bar(1, close=100, symbol="BTCUSDT"),
            _bar(2, close=102, symbol="BTCUSDT"),
            _bar(1, close=10, symbol="ETHUSDT"),
            _bar(2, close=11, symbol="ETHUSDT"),
        ],
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=2),
        higher_timeframe_rows=[
            _bar(2, close=1000, timeframe="2m", symbol="BTCUSDT"),
            _bar(2, close=2000, timeframe="2m", symbol="ETHUSDT"),
        ],
    )

    by_symbol = {row["symbol"]: [] for row in frame.rows}
    for row in frame.rows:
        by_symbol[row["symbol"]].append(row)

    assert by_symbol["BTCUSDT"][0]["return_1"] is None
    assert by_symbol["ETHUSDT"][0]["return_1"] is None
    assert by_symbol["BTCUSDT"][1]["return_1"] == pytest.approx(0.02)
    assert by_symbol["ETHUSDT"][1]["return_1"] == pytest.approx(0.1)
    assert by_symbol["BTCUSDT"][1]["htf_close"] == 1000.0
    assert by_symbol["ETHUSDT"][1]["htf_close"] == 2000.0
