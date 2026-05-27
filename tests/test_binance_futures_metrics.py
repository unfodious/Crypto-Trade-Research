from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.binance_futures_metrics import (
    BinanceFuturesMetricsDatasetConfig,
    BinanceFuturesMetricsDatasetError,
    generate_binance_futures_metrics_dataset,
)

CSV_HEADER = (
    "create_time,symbol,sum_open_interest,sum_open_interest_value,"
    "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
    "count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
)


def test_generate_binance_futures_metrics_dataset_writes_manifest_and_parquet(
    tmp_path: Path,
) -> None:
    manifest = generate_binance_futures_metrics_dataset(
        BinanceFuturesMetricsDatasetConfig(
            symbols=("BTCUSDT", "ETHUSDT"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            output_dir=tmp_path,
            dataset_name="unit_futures_metrics",
            generator_version="unit.v1",
            generated_at=datetime(2026, 1, 3, tzinfo=UTC),
            max_workers=2,
        ),
        fetch_zip=_fake_fetch_zip(
            {
                "BTCUSDT": [
                    "2026-01-01 00:10:00,BTCUSDT,11,1010,1.11,1.21,1.31,0.91",
                    "2026-01-01 00:05:00,BTCUSDT,10,1000,1.10,1.20,1.30,0.90",
                ],
                "ETHUSDT": [
                    "2026-01-01 00:05:00,ETHUSDT,20,2000,0.90,0.95,1.10,1.05",
                ],
            }
        ),
    )

    assert manifest.row_count == 3
    assert manifest.symbols == ("BTCUSDT", "ETHUSDT")
    assert manifest.min_metrics_time == "2026-01-01T00:05:00Z"
    assert manifest.max_metrics_time == "2026-01-01T00:10:00Z"
    assert manifest.source_file_count == 2
    assert manifest.missing_file_count == 0
    assert manifest.warnings == ()

    manifest_payload = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["source"]["format"] == "binance_data_vision_usdm_daily_metrics_zip"
    assert manifest_payload["source"]["end_date_exclusive"] is True
    assert len(manifest_payload["raw_sha256"]) == 64
    assert len(manifest_payload["cleaned_sha256"]) == 64

    table = pq.read_table(manifest.cleaned_path)
    rows = table.to_pylist()
    assert [(row["symbol"], row["metrics_time"]) for row in rows] == [
        ("BTCUSDT", datetime(2026, 1, 1, 0, 5, tzinfo=UTC)),
        ("BTCUSDT", datetime(2026, 1, 1, 0, 10, tzinfo=UTC)),
        ("ETHUSDT", datetime(2026, 1, 1, 0, 5, tzinfo=UTC)),
    ]
    assert rows[0]["data_source"] == "binance_data_vision_usdm_daily_metrics"
    assert rows[0]["source_file"] == "BTCUSDT-metrics-2026-01-01.zip"


def test_generate_binance_futures_metrics_dataset_rejects_duplicate_rows(
    tmp_path: Path,
) -> None:
    with pytest.raises(BinanceFuturesMetricsDatasetError, match="duplicate metrics row"):
        generate_binance_futures_metrics_dataset(
            BinanceFuturesMetricsDatasetConfig(
                symbols=("BTCUSDT",),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 2),
                output_dir=tmp_path,
                dataset_name="duplicate_futures_metrics",
                generator_version="unit.v1",
            ),
            fetch_zip=_fake_fetch_zip(
                {
                    "BTCUSDT": [
                        "2026-01-01 00:05:00,BTCUSDT,10,1000,1.10,1.20,1.30,0.90",
                        "2026-01-01 00:05:00,BTCUSDT,10,1000,1.10,1.20,1.30,0.90",
                    ],
                }
            ),
        )


def test_generate_binance_futures_metrics_dataset_can_record_missing_files(
    tmp_path: Path,
) -> None:
    manifest = generate_binance_futures_metrics_dataset(
        BinanceFuturesMetricsDatasetConfig(
            symbols=("BTCUSDT", "ETHUSDT"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            output_dir=tmp_path,
            dataset_name="missing_futures_metrics",
            generator_version="unit.v1",
            allow_missing_files=True,
        ),
        fetch_zip=_fake_fetch_zip(
            {
                "BTCUSDT": [
                    "2026-01-01 00:05:00,BTCUSDT,10,1000,1.10,1.20,1.30,0.90",
                ],
            }
        ),
    )

    assert manifest.row_count == 1
    assert manifest.source_file_count == 1
    assert manifest.missing_file_count == 1
    assert manifest.symbols == ("BTCUSDT",)
    assert len(manifest.warnings) == 1
    assert "missing metrics file:" in manifest.warnings[0]


def test_generate_binance_futures_metrics_dataset_keeps_blank_ratio_values_nullable(
    tmp_path: Path,
) -> None:
    manifest = generate_binance_futures_metrics_dataset(
        BinanceFuturesMetricsDatasetConfig(
            symbols=("BTCUSDT",),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            output_dir=tmp_path,
            dataset_name="nullable_futures_metrics",
            generator_version="unit.v1",
        ),
        fetch_zip=_fake_fetch_zip(
            {
                "BTCUSDT": [
                    "2026-01-01 00:05:00,BTCUSDT,10,1000,,1.20,1.30,",
                ],
            }
        ),
    )

    rows = pq.read_table(manifest.cleaned_path).to_pylist()
    assert rows[0]["count_toptrader_long_short_ratio"] is None
    assert rows[0]["sum_taker_long_short_vol_ratio"] is None
    assert "count_toptrader_long_short_ratio has 1 null source values" in manifest.warnings
    assert "sum_taker_long_short_vol_ratio has 1 null source values" in manifest.warnings


def _fake_fetch_zip(rows_by_symbol: dict[str, list[str]]):
    def fetch(url: str) -> bytes:
        for symbol, rows in rows_by_symbol.items():
            if f"/{symbol}/" in url:
                return _zip_csv(f"{Path(url).stem}.csv", rows)
        raise FileNotFoundError(url)

    return fetch


def _zip_csv(csv_name: str, rows: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(csv_name, CSV_HEADER + "\n".join(rows) + "\n")
    return buffer.getvalue()
