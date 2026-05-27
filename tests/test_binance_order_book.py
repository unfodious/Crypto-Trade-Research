import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.binance_order_book import (
    BinanceOrderBookSnapshotConfig,
    BinanceOrderBookSnapshotError,
    generate_binance_order_book_snapshot,
)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _depth_payload(symbol: str, event_time: datetime) -> dict[str, object]:
    price_shift = 0 if symbol == "BTCUSDT" else 100
    return {
        "lastUpdateId": 123456 + price_shift,
        "E": _ms(event_time),
        "T": _ms(event_time),
        "bids": [
            [str(99 + price_shift), "10"],
            [str(98 + price_shift), "50"],
        ],
        "asks": [
            [str(101 + price_shift), "20"],
            [str(102 + price_shift), "5"],
        ],
    }


def test_generate_binance_order_book_snapshot_writes_manifest_and_run_summary(
    tmp_path: Path,
) -> None:
    generated_at = datetime(2026, 5, 27, 10, 45, tzinfo=UTC)
    event_time = datetime(2026, 5, 27, 10, 44, tzinfo=UTC)
    calls: list[tuple[str, int, str]] = []

    def fetch_depth(symbol: str, limit: int, base_url: str) -> dict[str, object]:
        calls.append((symbol, limit, base_url))
        return _depth_payload(symbol, event_time)

    manifest = generate_binance_order_book_snapshot(
        BinanceOrderBookSnapshotConfig(
            symbols=("BTCUSDT", "ETHUSDT"),
            output_dir=tmp_path,
            dataset_prefix="unit_binance_order_book",
            generator_version="unit.order_book.v1",
            generated_at=generated_at,
            limit=5,
            request_sleep_seconds=0,
        ),
        fetch_depth=fetch_depth,
    )

    assert manifest.row_count == 10
    assert manifest.summary_row_count == 2
    assert manifest.level_row_count == 8
    assert manifest.symbols == ("BTCUSDT", "ETHUSDT")
    assert manifest.summary_path.exists()
    assert manifest.levels_path.exists()
    assert manifest.manifest_path.exists()
    assert len(manifest.summary_sha256) == 64
    assert len(manifest.levels_sha256) == 64

    summary_rows = pq.read_table(manifest.summary_path).to_pylist()
    btc_summary = next(row for row in summary_rows if row["symbol"] == "BTCUSDT")
    assert btc_summary["event_time"] == event_time
    assert btc_summary["source_available_at"] == generated_at
    assert btc_summary["best_bid_price"] == pytest.approx(99.0)
    assert btc_summary["best_ask_price"] == pytest.approx(101.0)
    assert btc_summary["mid_price"] == pytest.approx(100.0)
    assert btc_summary["spread_bps"] == pytest.approx(200.0)
    assert btc_summary["bid_notional_total"] == pytest.approx(5890.0)
    assert btc_summary["ask_notional_total"] == pytest.approx(2530.0)
    assert btc_summary["notional_imbalance"] == pytest.approx((5890 - 2530) / (5890 + 2530))
    assert btc_summary["largest_bid_notional"] == pytest.approx(4900.0)
    assert btc_summary["largest_bid_distance_bps"] == pytest.approx(200.0)
    assert btc_summary["largest_ask_notional"] == pytest.approx(2020.0)
    assert btc_summary["largest_ask_distance_bps"] == pytest.approx(100.0)
    assert btc_summary["levels_per_side"] == 2

    level_rows = pq.read_table(manifest.levels_path).to_pylist()
    assert len(level_rows) == 8
    first_bid = next(
        row for row in level_rows if row["symbol"] == "BTCUSDT" and row["side"] == "bid"
    )
    assert first_bid["level"] == 1
    assert first_bid["notional"] == pytest.approx(990.0)
    assert first_bid["distance_bps"] == pytest.approx(100.0)

    manifest_json = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert manifest_json["schema_version"] == "research.binance_futures_order_book_snapshot.v1"
    assert manifest_json["source"]["history_limit_note"]
    assert manifest_json["summary_path"] == str(manifest.summary_path)
    assert manifest_json["levels_path"] == str(manifest.levels_path)

    run_summary = json.loads(
        (tmp_path / "unit_binance_order_book" / "order_book_run.json").read_text(encoding="utf-8")
    )
    assert run_summary["schema_version"] == "research.binance_futures_order_book_run.v1"
    assert run_summary["latest_manifest_path"] == str(manifest.manifest_path)
    assert run_summary["row_count"] == 10
    assert run_summary["summary_row_count"] == 2
    assert run_summary["level_row_count"] == 8
    assert calls[0] == ("BTCUSDT", 5, "https://fapi.binance.com/fapi/v1/depth")


def test_generate_binance_order_book_snapshot_preserves_partial_source_warnings(
    tmp_path: Path,
) -> None:
    generated_at = datetime(2026, 5, 27, 10, 45, tzinfo=UTC)
    event_time = datetime(2026, 5, 27, 10, 44, tzinfo=UTC)

    def fetch_depth(symbol: str, limit: int, base_url: str) -> dict[str, object]:
        if symbol == "ETHUSDT":
            raise RuntimeError("rate limited")
        return _depth_payload(symbol, event_time)

    manifest = generate_binance_order_book_snapshot(
        BinanceOrderBookSnapshotConfig(
            symbols=("BTCUSDT", "ETHUSDT"),
            output_dir=tmp_path,
            dataset_prefix="unit_binance_order_book",
            generator_version="unit.order_book.v1",
            generated_at=generated_at,
            limit=5,
            request_sleep_seconds=0,
        ),
        fetch_depth=fetch_depth,
    )

    assert manifest.row_count == 5
    assert manifest.summary_row_count == 1
    assert manifest.level_row_count == 4
    assert len(manifest.warnings) == 1
    assert "ETHUSDT order-book depth failed: rate limited" in manifest.warnings[0]


def test_binance_order_book_snapshot_rejects_empty_source(tmp_path: Path) -> None:
    def fail_depth(symbol: str, limit: int, base_url: str) -> dict[str, object]:
        raise RuntimeError("offline")

    with pytest.raises(BinanceOrderBookSnapshotError, match="all Binance order-book sources"):
        generate_binance_order_book_snapshot(
            BinanceOrderBookSnapshotConfig(
                symbols=("BTCUSDT",),
                output_dir=tmp_path,
                dataset_prefix="unit_binance_order_book",
                generator_version="unit.order_book.v1",
                limit=5,
                request_sleep_seconds=0,
            ),
            fetch_depth=fail_depth,
        )


def test_binance_order_book_snapshot_rejects_unsupported_limit(tmp_path: Path) -> None:
    with pytest.raises(BinanceOrderBookSnapshotError, match="unsupported Binance order-book"):
        generate_binance_order_book_snapshot(
            BinanceOrderBookSnapshotConfig(
                symbols=("BTCUSDT",),
                output_dir=tmp_path,
                dataset_prefix="unit_binance_order_book",
                generator_version="unit.order_book.v1",
                limit=2,
                request_sleep_seconds=0,
            ),
            fetch_depth=lambda symbol, limit, base_url: _depth_payload(
                symbol,
                datetime(2026, 5, 27, 10, 44, tzinfo=UTC),
            ),
        )
