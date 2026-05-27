import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.ingestion import (
    DatasetValidationError,
    MarketDatasetConfig,
    generate_market_dataset,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _base_row(
    open_time: str,
    close_time: str,
    close: str = "42020.0",
    timeframe: str = "1m",
) -> dict[str, str]:
    return {
        "schema_version": "research.dataset.v1",
        "venue": "Binance",
        "market_type": "UM_FUTURES",
        "symbol": "btcusdt",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "timeframe": timeframe,
        "open_time": open_time,
        "close_time": close_time,
        "source_available_at": close_time,
        "open": "42000.0",
        "high": "42110.0",
        "low": "41980.0",
        "close": close,
        "volume": "12.5",
        "quote_volume": "525250.0",
        "number_of_trades": "120",
        "taker_buy_base_volume": "6.0",
        "taker_buy_quote_volume": "252120.0",
        "data_source": "fixture:unit-test",
        "source_file": "unit.csv",
        "checksum": "sha256:unit",
    }


def test_generate_market_dataset_writes_sorted_parquet_and_manifest(tmp_path: Path) -> None:
    source_csv = tmp_path / "market_candles.csv"
    output_dir = tmp_path / "dataset"
    generated_at = datetime(2026, 5, 25, 12, 0, tzinfo=UTC)
    rows = [
        _base_row("2026-01-01T00:01:00Z", "2026-01-01T00:02:00Z", close="42090.0"),
        _base_row("2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"),
        _base_row(
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:05:00Z",
            close="42100.0",
            timeframe="5m",
        ),
    ]
    _write_csv(source_csv, rows)

    manifest = generate_market_dataset(
        MarketDatasetConfig(
            source_csv=source_csv,
            output_dir=output_dir,
            dataset_name="unit_dataset",
            generator_version="test.v1",
            generated_at=generated_at,
        )
    )

    assert manifest.row_count == 3
    assert manifest.min_close_time == "2026-01-01T00:01:00Z"
    assert manifest.max_close_time == "2026-01-01T00:05:00Z"
    assert manifest.raw_path.exists()
    assert manifest.cleaned_path.exists()
    assert manifest.manifest_path.exists()
    assert len(manifest.source_sha256) == 64
    assert len(manifest.raw_sha256) == 64
    assert len(manifest.cleaned_sha256) == 64

    clean_table = pq.read_table(manifest.cleaned_path)
    assert clean_table.column("symbol").to_pylist() == ["BTCUSDT", "BTCUSDT", "BTCUSDT"]
    assert clean_table.column("venue").to_pylist() == ["binance", "binance", "binance"]
    assert clean_table.column("timeframe").to_pylist() == ["1m", "1m", "5m"]
    assert clean_table.column("close_time").to_pylist() == [
        datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
    ]

    manifest_json = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert manifest_json["schema_version"] == "research.dataset.v1"
    assert manifest_json["source"]["format"] == "csv"
    assert manifest_json["generated_at"] == "2026-05-25T12:00:00Z"
    assert manifest_json["source_sha256"] == manifest.source_sha256
    assert manifest_json["raw_sha256"] == manifest.raw_sha256
    assert manifest_json["cleaned_sha256"] == manifest.cleaned_sha256


def test_generate_market_dataset_rejects_duplicate_candles(tmp_path: Path) -> None:
    source_csv = tmp_path / "market_candles.csv"
    row = _base_row("2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z")
    _write_csv(source_csv, [row, row])

    with pytest.raises(DatasetValidationError, match="duplicate candle key"):
        generate_market_dataset(
            MarketDatasetConfig(
                source_csv=source_csv,
                output_dir=tmp_path / "dataset",
                dataset_name="duplicate_dataset",
                generator_version="test.v1",
                generated_at=datetime(2026, 5, 25, 12, 0, tzinfo=UTC),
            )
        )


def test_raw_signal_rows_do_not_include_future_label_fields(tmp_path: Path) -> None:
    source_csv = tmp_path / "market_candles.csv"
    _write_csv(
        source_csv,
        [_base_row("2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z")],
    )

    manifest = generate_market_dataset(
        MarketDatasetConfig(
            source_csv=source_csv,
            output_dir=tmp_path / "dataset",
            dataset_name="leakage_dataset",
            generator_version="test.v1",
            generated_at=datetime(2026, 5, 25, 12, 0, tzinfo=UTC),
        )
    )

    raw_columns = set(pq.read_table(manifest.raw_path).column_names)
    assert "forward_return_1" not in raw_columns
    assert "target_before_stop" not in raw_columns
    assert "expected_r_after_costs" not in raw_columns


def test_generate_market_dataset_accepts_crypto_flash_crash_candle(tmp_path: Path) -> None:
    source_csv = tmp_path / "market_candles.csv"
    row = _base_row("2025-10-10T21:22:00Z", "2025-10-10T21:23:00Z")
    row.update(
        {
            "symbol": "avaxusdt",
            "base_asset": "AVAX",
            "open": "11.729",
            "high": "18.164",
            "low": "11.703",
            "close": "17.935",
            "volume": "526716",
            "quote_volume": "7818849.472",
            "number_of_trades": "11982",
            "taker_buy_base_volume": "310000",
            "taker_buy_quote_volume": "4600000",
            "source_file": "AVAXUSDT-1m-2025-10-10.csv",
        }
    )
    _write_csv(source_csv, [row])

    manifest = generate_market_dataset(
        MarketDatasetConfig(
            source_csv=source_csv,
            output_dir=tmp_path / "dataset",
            dataset_name="flash_crash_dataset",
            generator_version="test.v1",
            generated_at=datetime(2026, 5, 25, 12, 0, tzinfo=UTC),
        )
    )

    assert manifest.row_count == 1
