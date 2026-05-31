from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.book_depth_selected_features import (
    BookDepthSelectedFeaturesConfig,
    BookDepthSelectedWindowConfig,
    build_book_depth_selected_features,
)


def test_build_book_depth_selected_features_uses_point_in_time_lookup(
    tmp_path: Path,
) -> None:
    book_depth_path = tmp_path / "book_depth_features.parquet"
    selected_path = tmp_path / "selected_trades.parquet"
    output_path = tmp_path / "joined.parquet"
    _write_parquet(
        book_depth_path,
        [
            _feature_row("BTCUSDT", "2026-01-01T00:00:00Z", imbalance=-0.25),
            _feature_row("BTCUSDT", "2026-01-01T00:05:00Z", imbalance=0.50),
            _feature_row("ETHUSDT", "2026-01-01T00:02:00Z", imbalance=0.10),
        ],
    )
    _write_parquet(
        selected_path,
        [
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "decision_time": datetime(2026, 1, 1, 0, 4, tzinfo=UTC),
            },
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "decision_time": datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
            },
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "decision_time": datetime(2026, 1, 1, 0, 9, tzinfo=UTC),
            },
        ],
    )

    summary = build_book_depth_selected_features(
        BookDepthSelectedFeaturesConfig(
            book_depth_features_path=book_depth_path,
            max_depth_age_minutes=5,
            windows=(
                BookDepthSelectedWindowConfig(
                    name="unit",
                    selected_trades_path=selected_path,
                    output_path=output_path,
                ),
            ),
        )
    )

    assert summary["windows"][0]["row_count"] == 3
    assert summary["windows"][0]["matched_book_depth_count"] == 2
    rows = pq.read_table(output_path).to_pylist()
    assert rows[0]["bd_match"] == 1
    assert rows[0]["bd_age_minutes"] == 4.0
    assert rows[0]["bd_imbalance_1pct"] == -0.25
    assert rows[1]["bd_match"] == 1
    assert rows[1]["bd_age_minutes"] == 0.0
    assert rows[1]["bd_imbalance_1pct"] == 0.50
    assert rows[2]["bd_match"] == 0
    assert rows[2]["bd_imbalance_1pct"] is None


def _feature_row(symbol: str, depth_time: str, *, imbalance: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "depth_time": depth_time,
        "bd_bid_notional_1pct": 100.0,
        "bd_bid_notional_2pct": 200.0,
        "bd_bid_notional_5pct": 500.0,
        "bd_ask_notional_1pct": 100.0,
        "bd_ask_notional_2pct": 200.0,
        "bd_ask_notional_5pct": 500.0,
        "bd_imbalance_1pct": imbalance,
        "bd_imbalance_2pct": imbalance,
        "bd_imbalance_5pct": imbalance,
        "bd_total_notional_1pct": 200.0,
        "bd_total_notional_2pct": 400.0,
        "bd_total_notional_5pct": 1000.0,
    }


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)
