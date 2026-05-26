from datetime import UTC, datetime

import pytest

from crypto_trade_research.features import FeatureConfig, generate_ohlcv_features
from crypto_trade_research.labels.outcomes import (
    LabelConfig,
    generate_trade_labels,
)


def _ts(minute: int) -> datetime:
    return datetime(2026, 1, 1, 0, minute, tzinfo=UTC)


def _bar(
    minute: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    symbol: str = "BTCUSDT",
) -> dict[str, object]:
    return {
        "schema_version": "research.dataset.v1",
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": symbol,
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "timeframe": "1m",
        "open_time": _ts(minute - 1),
        "close_time": _ts(minute),
        "source_available_at": _ts(minute),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100.0,
    }


def test_long_trade_labels_target_before_stop_and_r_multiple() -> None:
    frame = generate_trade_labels(
        [
            _bar(1, 100, 101, 99, 100),
            _bar(2, 100, 103, 99.5, 102),
            _bar(3, 102, 106, 101, 105),
            _bar(4, 105, 107, 104, 106),
        ],
        LabelConfig(
            label_set_version="unit.labels.v1",
            horizon_bars=3,
            side="long",
            stop_loss_pct=0.02,
            target_pct=0.04,
            cost_pct=0.001,
            flat_threshold_pct=0.001,
        ),
    )

    first = frame.rows[0]
    assert first["decision_time"] == _ts(1)
    assert first["entry_price"] == 100.0
    assert first["stop_price"] == 98.0
    assert first["target_price"] == 104.0
    assert first["target_before_stop"] is True
    assert first["time_to_target_bars"] == 2
    assert first["time_to_stop_bars"] is None
    assert first["max_favorable_excursion_r"] == pytest.approx(3.5)
    assert first["max_adverse_excursion_r"] == pytest.approx(-0.25)
    assert first["realized_r_after_costs"] == pytest.approx(1.95)
    assert first["directional_class"] == "up"

    assert frame.manifest.label_set_version == "unit.labels.v1"
    assert frame.manifest.row_count == 4
    assert all(spec.availability == "after_the_fact" for spec in frame.manifest.labels)


def test_short_trade_labels_stop_before_target() -> None:
    frame = generate_trade_labels(
        [
            _bar(1, 100, 101, 99, 100),
            _bar(2, 100, 103, 99, 102),
            _bar(3, 102, 104, 101, 103),
        ],
        LabelConfig(
            label_set_version="unit.labels.v1",
            horizon_bars=2,
            side="short",
            stop_loss_pct=0.02,
            target_pct=0.03,
            cost_pct=0.001,
            flat_threshold_pct=0.001,
        ),
    )

    first = frame.rows[0]
    assert first["stop_price"] == 102.0
    assert first["target_price"] == 97.0
    assert first["target_before_stop"] is False
    assert first["time_to_stop_bars"] == 1
    assert first["time_to_target_bars"] is None
    assert first["realized_r_after_costs"] == pytest.approx(-1.05)
    assert first["directional_class"] == "down"


def test_same_bar_target_stop_ambiguity_defaults_to_stop_first_for_long() -> None:
    frame = generate_trade_labels(
        [
            _bar(1, 100, 101, 99, 100),
            _bar(2, 100, 105, 97, 101),
        ],
        LabelConfig(
            label_set_version="unit.labels.v1",
            horizon_bars=1,
            side="long",
            stop_loss_pct=0.02,
            target_pct=0.04,
            cost_pct=0.001,
            flat_threshold_pct=0.001,
        ),
    )

    first = frame.rows[0]
    assert first["time_to_target_bars"] == 1
    assert first["time_to_stop_bars"] == 1
    assert first["target_before_stop"] is False
    assert first["realized_r_after_costs"] == pytest.approx(-1.05)


def test_same_bar_target_stop_ambiguity_can_be_marked_target_first_for_sensitivity() -> None:
    frame = generate_trade_labels(
        [
            _bar(1, 100, 101, 99, 100),
            _bar(2, 100, 103, 97, 99),
        ],
        LabelConfig(
            label_set_version="unit.labels.v1",
            horizon_bars=1,
            side="short",
            stop_loss_pct=0.02,
            target_pct=0.03,
            cost_pct=0.001,
            flat_threshold_pct=0.001,
            target_stop_tie_breaker="target_first",
        ),
    )

    first = frame.rows[0]
    assert first["time_to_target_bars"] == 1
    assert first["time_to_stop_bars"] == 1
    assert first["target_before_stop"] is True
    assert first["realized_r_after_costs"] == pytest.approx(1.45)


def test_label_rows_join_features_without_leaking_label_fields() -> None:
    bars = [
        _bar(1, 100, 101, 99, 100),
        _bar(2, 100, 102, 99, 101),
        _bar(3, 101, 103, 100, 102),
    ]
    features = generate_ohlcv_features(
        bars,
        FeatureConfig(feature_set_version="unit.features.v1", rolling_window=2),
    )
    labels = generate_trade_labels(
        bars,
        LabelConfig(
            label_set_version="unit.labels.v1",
            horizon_bars=2,
            side="long",
            stop_loss_pct=0.02,
            target_pct=0.03,
            cost_pct=0.001,
            flat_threshold_pct=0.02,
        ),
    )

    feature_keys = {
        (row["symbol"], row["timeframe"], row["decision_time"]) for row in features.rows
    }
    label_keys = {(row["symbol"], row["timeframe"], row["decision_time"]) for row in labels.rows}
    assert feature_keys == label_keys
    assert "target_before_stop" not in features.rows[0]
    assert labels.rows[0]["directional_class"] == "flat"
    assert labels.rows[-1]["no_trade_reason"] == "insufficient_future_window"


def test_label_future_windows_do_not_cross_symbol_boundaries() -> None:
    frame = generate_trade_labels(
        [
            _bar(1, 100, 101, 99, 100, symbol="BTCUSDT"),
            _bar(2, 100, 103, 99, 102, symbol="BTCUSDT"),
            _bar(1, 10, 11, 9, 10, symbol="ETHUSDT"),
            _bar(2, 10, 10.5, 9.5, 10.1, symbol="ETHUSDT"),
        ],
        LabelConfig(
            label_set_version="unit.labels.v1",
            horizon_bars=2,
            side="long",
            stop_loss_pct=0.02,
            target_pct=0.04,
            cost_pct=0.001,
            flat_threshold_pct=0.001,
        ),
    )

    by_symbol = {row["symbol"]: [] for row in frame.rows}
    for row in frame.rows:
        by_symbol[row["symbol"]].append(row)

    assert by_symbol["BTCUSDT"][0]["no_trade_reason"] == "insufficient_future_window"
    assert by_symbol["ETHUSDT"][0]["no_trade_reason"] == "insufficient_future_window"
    assert by_symbol["BTCUSDT"][1]["source_window_start"] is None
    assert by_symbol["ETHUSDT"][1]["source_window_start"] is None
