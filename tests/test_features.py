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
    taker_buy_base_volume: float | None = None,
    number_of_trades: int = 10,
    timeframe: str = "1m",
    symbol: str = "BTCUSDT",
) -> dict[str, object]:
    taker_buy_base = volume / 2 if taker_buy_base_volume is None else taker_buy_base_volume
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
        "quote_volume": volume * close,
        "number_of_trades": number_of_trades,
        "taker_buy_base_volume": taker_buy_base,
        "taker_buy_quote_volume": taker_buy_base * close,
    }


def _funding(
    minute: int,
    symbol: str,
    funding_rate: float,
    mark_price: float = 100.0,
) -> dict[str, object]:
    timestamp = datetime(2026, 1, 1, 0, minute, tzinfo=UTC)
    return {
        "schema_version": "research.funding_rate.v1",
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": symbol,
        "funding_time": timestamp,
        "source_available_at": timestamp,
        "funding_rate": funding_rate,
        "mark_price": mark_price,
        "data_source": "binance_fapi_funding_rate",
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
        "trend_above_ma_3",
        "ma_slope_sign_3",
        "range_position_3",
        "volume_zscore_3",
        "relative_volume_3",
        "taker_buy_base_ratio",
        "taker_buy_quote_ratio",
        "taker_flow_imbalance",
        "taker_flow_imbalance_zscore_3",
        "taker_buy_base_ratio_mean_3",
        "trade_count_zscore_3",
        "volatility_bucket_3",
        "realized_volatility_3",
        "ema_3",
        "rsi_3",
        "stochastic_k_3",
        "atr_3",
        "normalized_atr_3",
        "bollinger_position_3",
        "bollinger_width_3",
        "macd_3",
        "macd_signal_3",
        "macd_histogram_3",
        "dmi_plus_3",
        "dmi_minus_3",
        "adx_3",
        "body_pressure",
        "wick_pressure",
        "consecutive_bull_bars",
        "consecutive_bear_bars",
        "candle_body_pct",
        "close_location",
    } <= feature_names
    assert all(spec.availability == "post_close" for spec in frame.manifest.features)

    first_row = frame.rows[0]
    assert first_row["return_1"] is None
    assert first_row["roc_2"] is None
    assert first_row["ma_3"] is None
    assert first_row["rsi_3"] is None
    assert first_row["atr_3"] is None
    assert first_row["warmup_missing_bars"] == 2

    last_row = frame.rows[-1]
    assert last_row["decision_time"] == _ts(4)
    assert last_row["return_1"] == pytest.approx(0.0297029702970297)
    assert last_row["roc_2"] == pytest.approx(0.0196078431372549)
    assert last_row["ma_3"] == pytest.approx(102.33333333333333)
    assert last_row["trend_above_ma_3"] == 1.0
    assert last_row["ma_slope_sign_3"] == 1.0
    assert last_row["range_position_3"] == pytest.approx(5 / 7)
    assert last_row["volume_zscore_3"] == pytest.approx(1.0690449676496976)
    assert last_row["relative_volume_3"] == pytest.approx(140 / (340 / 3))
    assert last_row["taker_buy_base_ratio"] == pytest.approx(0.5)
    assert last_row["taker_buy_quote_ratio"] == pytest.approx(0.5)
    assert last_row["taker_flow_imbalance"] == pytest.approx(0.0)
    assert last_row["taker_buy_base_ratio_mean_3"] == pytest.approx(0.5)
    assert last_row["volatility_bucket_3"] == 1.0
    assert last_row["ema_3"] == pytest.approx(102.75)
    assert last_row["rsi_3"] == pytest.approx(75.0)
    assert last_row["stochastic_k_3"] == pytest.approx(5 / 7)
    assert last_row["atr_3"] == pytest.approx(13 / 3)
    assert last_row["normalized_atr_3"] == pytest.approx((13 / 3) / 104)
    assert last_row["bollinger_position_3"] == pytest.approx(0.8340765523905306)
    assert last_row["bollinger_width_3"] == pytest.approx(0.048751236309758195)
    assert last_row["macd_3"] == pytest.approx(0.25)
    assert last_row["macd_signal_3"] == pytest.approx(0.2777777777777768)
    assert last_row["macd_histogram_3"] == pytest.approx(-0.02777777777777679)
    assert last_row["dmi_plus_3"] == pytest.approx(500 / 13)
    assert last_row["dmi_minus_3"] == pytest.approx(100 / 13)
    assert last_row["adx_3"] == pytest.approx(200 / 3)
    assert last_row["body_pressure"] == pytest.approx(0.25)
    assert last_row["wick_pressure"] == pytest.approx(-0.25)
    assert last_row["consecutive_bull_bars"] == 4.0
    assert last_row["consecutive_bear_bars"] == 0.0


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
    assert by_symbol["BTCUSDT"][0]["trend_above_ma_2"] is None
    assert by_symbol["ETHUSDT"][0]["trend_above_ma_2"] is None
    assert by_symbol["BTCUSDT"][1]["trend_above_ma_2"] == 1.0
    assert by_symbol["ETHUSDT"][1]["trend_above_ma_2"] == 1.0
    assert by_symbol["BTCUSDT"][1]["htf_close"] == 1000.0
    assert by_symbol["ETHUSDT"][1]["htf_close"] == 2000.0


def test_regime_features_bucket_volatility_and_trend_point_in_time() -> None:
    frame = generate_ohlcv_features(
        [
            _bar(1, close=100, high=101, low=99),
            _bar(2, close=101, high=102, low=100),
            _bar(3, close=102, high=103, low=101),
            _bar(4, close=103, high=110, low=96),
            _bar(5, close=101, high=102, low=100),
        ],
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=3),
    )

    warmup_row = frame.rows[1]
    assert warmup_row["trend_above_ma_3"] is None
    assert warmup_row["ma_slope_sign_3"] is None
    assert warmup_row["volatility_bucket_3"] is None

    expanded_row = frame.rows[3]
    assert expanded_row["trend_above_ma_3"] == 1.0
    assert expanded_row["ma_slope_sign_3"] == 1.0
    assert expanded_row["volatility_expansion_3"] == pytest.approx(14 / 6)
    assert expanded_row["volatility_bucket_3"] == 2.0

    downtrend_row = frame.rows[4]
    assert downtrend_row["trend_above_ma_3"] == 0.0
    assert downtrend_row["ma_slope_sign_3"] == 0.0


def test_taker_flow_features_use_current_and_rolling_closed_bars() -> None:
    frame = generate_ohlcv_features(
        [
            _bar(1, close=100, volume=100, taker_buy_base_volume=20, number_of_trades=10),
            _bar(2, close=101, volume=100, taker_buy_base_volume=50, number_of_trades=20),
            _bar(3, close=102, volume=100, taker_buy_base_volume=80, number_of_trades=40),
        ],
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=3),
    )

    first_row = frame.rows[0]
    assert first_row["taker_buy_base_ratio"] == pytest.approx(0.2)
    assert first_row["taker_flow_imbalance"] == pytest.approx(-0.6)
    assert first_row["taker_flow_imbalance_zscore_3"] is None

    last_row = frame.rows[-1]
    assert last_row["taker_buy_base_ratio"] == pytest.approx(0.8)
    assert last_row["taker_buy_quote_ratio"] == pytest.approx(0.8)
    assert last_row["taker_flow_imbalance"] == pytest.approx(0.6)
    assert last_row["taker_buy_base_ratio_mean_3"] == pytest.approx(0.5)
    assert last_row["taker_flow_imbalance_zscore_3"] == pytest.approx(1.224744871391589)
    assert last_row["trade_count_zscore_3"] == pytest.approx(1.3363062095621219)


def test_market_context_features_use_same_timestamp_reference_rows() -> None:
    frame = generate_ohlcv_features(
        [
            _bar(1, close=100, symbol="BTCUSDT", taker_buy_base_volume=70),
            _bar(2, close=102, symbol="BTCUSDT", taker_buy_base_volume=80),
            _bar(3, close=101, symbol="BTCUSDT", taker_buy_base_volume=60),
            _bar(1, close=50, symbol="ETHUSDT", taker_buy_base_volume=40),
            _bar(2, close=49, symbol="ETHUSDT", taker_buy_base_volume=30),
            _bar(3, close=51, symbol="ETHUSDT", taker_buy_base_volume=35),
            _bar(1, close=10, symbol="ADAUSDT", taker_buy_base_volume=50),
            _bar(2, close=11, symbol="ADAUSDT", taker_buy_base_volume=55),
            _bar(3, close=12, symbol="ADAUSDT", taker_buy_base_volume=45),
        ],
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=2),
    )

    feature_names = {spec.name for spec in frame.manifest.features}
    assert {
        "market_positive_return_fraction",
        "market_average_return_1",
        "market_above_ma_fraction_2",
        "risk_on_score_2",
        "btc_return_1",
        "eth_return_1",
        "relative_strength_vs_btc_1",
        "relative_strength_vs_eth_1",
        "correlation_to_btc_2",
        "beta_to_btc_2",
        "market_taker_flow_imbalance",
        "btc_taker_flow_imbalance",
        "eth_taker_flow_imbalance",
        "relative_taker_flow_vs_btc",
    } <= feature_names

    ada_rows = [row for row in frame.rows if row["symbol"] == "ADAUSDT"]
    ada_second_row = ada_rows[1]
    assert ada_second_row["decision_time"] == _ts(2)
    assert ada_second_row["market_positive_return_fraction"] == pytest.approx(2 / 3)
    assert ada_second_row["market_average_return_1"] == pytest.approx((0.02 - 0.02 + 0.1) / 3)
    assert ada_second_row["market_above_ma_fraction_2"] == pytest.approx(2 / 3)
    assert ada_second_row["risk_on_score_2"] == pytest.approx(7 / 12)
    assert ada_second_row["btc_return_1"] == pytest.approx(0.02)
    assert ada_second_row["eth_return_1"] == pytest.approx(-0.02)
    assert ada_second_row["relative_strength_vs_btc_1"] == pytest.approx(0.08)
    assert ada_second_row["relative_strength_vs_eth_1"] == pytest.approx(0.12)
    assert ada_second_row["market_taker_flow_imbalance"] == pytest.approx(
        ((0.8 * 2 - 1) + (0.3 * 2 - 1) + (0.55 * 2 - 1)) / 3
    )
    assert ada_second_row["btc_taker_flow_imbalance"] == pytest.approx(0.6)
    assert ada_second_row["eth_taker_flow_imbalance"] == pytest.approx(-0.4)
    assert ada_second_row["relative_taker_flow_vs_btc"] == pytest.approx(-0.5)

    ada_third_row = ada_rows[2]
    assert ada_third_row["correlation_to_btc_2"] == pytest.approx(1.0)
    assert ada_third_row["correlation_to_eth_2"] == pytest.approx(-1.0)
    assert ada_third_row["beta_to_btc_2"] is not None
    assert ada_third_row["beta_to_eth_2"] is not None


def test_funding_features_use_only_available_funding_events() -> None:
    rows = []
    for symbol, base in (("BTCUSDT", 100), ("ETHUSDT", 50), ("ADAUSDT", 10)):
        rows.extend(
            [
                _bar(1, close=base, symbol=symbol),
                _bar(2, close=base + 1, symbol=symbol),
                _bar(3, close=base + 2, symbol=symbol),
            ]
        )

    frame = generate_ohlcv_features(
        rows,
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=2),
        funding_rate_rows=[
            _funding(0, "BTCUSDT", 0.0001),
            _funding(1, "BTCUSDT", 0.0003),
            _funding(0, "ETHUSDT", -0.0002),
            _funding(1, "ETHUSDT", -0.0001),
            _funding(0, "ADAUSDT", 0.0002),
            _funding(1, "ADAUSDT", 0.0004),
            _funding(8, "ADAUSDT", 0.01),
        ],
    )

    feature_names = {spec.name for spec in frame.manifest.features}
    assert {
        "funding_rate",
        "funding_rate_mean_2",
        "funding_rate_zscore_2",
        "funding_rate_abs_zscore_2",
        "funding_rate_positive",
        "funding_rate_abs",
        "hours_since_funding",
        "hours_to_next_funding_estimate",
        "market_average_funding_rate",
        "market_positive_funding_fraction",
        "btc_funding_rate",
        "eth_funding_rate",
        "relative_funding_vs_btc",
    } <= feature_names

    ada_rows = [row for row in frame.rows if row["symbol"] == "ADAUSDT"]
    first_row = ada_rows[0]
    assert first_row["funding_rate"] == pytest.approx(0.0004)
    assert first_row["funding_rate_mean_2"] == pytest.approx(0.0003)
    assert first_row["funding_rate_zscore_2"] == pytest.approx(1.0)
    assert first_row["funding_rate_abs_zscore_2"] == pytest.approx(1.0)
    assert first_row["funding_rate_positive"] == 1.0
    assert first_row["hours_since_funding"] == pytest.approx(0.0)
    assert first_row["hours_to_next_funding_estimate"] == pytest.approx(8.0)
    assert first_row["market_average_funding_rate"] == pytest.approx((0.0003 - 0.0001 + 0.0004) / 3)
    assert first_row["market_positive_funding_fraction"] == pytest.approx(2 / 3)
    assert first_row["btc_funding_rate"] == pytest.approx(0.0003)
    assert first_row["eth_funding_rate"] == pytest.approx(-0.0001)
    assert first_row["relative_funding_vs_btc"] == pytest.approx(0.0001)

    last_row = ada_rows[-1]
    assert last_row["decision_time"] == _ts(3)
    assert last_row["funding_rate"] == pytest.approx(0.0004)
    assert last_row["hours_since_funding"] == pytest.approx(2 / 60)


def test_derived_multi_timeframe_features_use_only_closed_candles() -> None:
    rows = []
    for symbol, base in (("BTCUSDT", 100), ("ETHUSDT", 50), ("ADAUSDT", 10)):
        rows.extend(
            [
                _bar(1, close=base, symbol=symbol),
                _bar(2, close=base + 2, symbol=symbol),
                _bar(3, close=base + 4, symbol=symbol),
                _bar(4, close=base + 6, symbol=symbol),
            ]
        )

    frame = generate_ohlcv_features(
        rows,
        FeatureConfig(
            feature_set_version="unit.features.v1",
            rolling_window=2,
            higher_timeframes=("2m",),
        ),
    )

    feature_names = {spec.name for spec in frame.manifest.features}
    assert {
        "mtf_2m_return_1",
        "mtf_2m_trend_above_ma_2",
        "mtf_2m_ma_slope_sign_2",
        "mtf_2m_range_position_2",
        "mtf_2m_volatility_bucket_2",
        "mtf_2m_market_positive_return_fraction",
        "mtf_2m_risk_on_score_2",
        "mtf_2m_btc_return_1",
        "mtf_2m_eth_return_1",
    } <= feature_names

    ada_rows = [row for row in frame.rows if row["symbol"] == "ADAUSDT"]
    assert ada_rows[2]["decision_time"] == _ts(3)
    assert ada_rows[2]["mtf_2m_return_1"] is None

    last_row = ada_rows[3]
    assert last_row["decision_time"] == _ts(4)
    assert last_row["mtf_2m_return_1"] == pytest.approx(16 / 12 - 1)
    assert last_row["mtf_2m_trend_above_ma_2"] == 1.0
    assert last_row["mtf_2m_ma_slope_sign_2"] is None
    assert last_row["mtf_2m_range_position_2"] == pytest.approx(0.8)
    assert last_row["mtf_2m_volatility_bucket_2"] == 1.0
    assert last_row["mtf_2m_market_positive_return_fraction"] == 1.0
    assert last_row["mtf_2m_risk_on_score_2"] == 1.0
    assert last_row["mtf_2m_btc_return_1"] == pytest.approx(106 / 102 - 1)
