from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.binance_book_depth import (
    BinanceBookDepthCoverageConfig,
    BinanceBookDepthDatasetConfig,
    BinanceBookDepthError,
    generate_binance_book_depth_dataset,
    write_binance_book_depth_coverage_report,
)

CSV_HEADER = "timestamp,percentage,depth,notional\n"
BANDS = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)


def test_generate_binance_book_depth_dataset_writes_manifest_depth_and_features(
    tmp_path: Path,
) -> None:
    manifest = generate_binance_book_depth_dataset(
        BinanceBookDepthDatasetConfig(
            symbols=("BTCUSDT",),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            output_dir=tmp_path,
            dataset_name="unit_book_depth",
            generator_version="unit.v1",
            generated_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
        fetch_zip=_fake_fetch_zip(
            {
                "BTCUSDT": [
                    _rows_for_timestamp("2026-01-01 00:00:01"),
                    _rows_for_timestamp("2026-01-01 00:00:31", bid_multiplier=2),
                ],
            }
        ),
    )

    assert manifest.row_count == 20
    assert manifest.feature_row_count == 2
    assert manifest.symbols == ("BTCUSDT",)
    assert manifest.min_depth_time == "2026-01-01T00:00:01Z"
    assert manifest.max_depth_time == "2026-01-01T00:00:31Z"
    assert manifest.source_file_count == 1
    assert manifest.missing_file_count == 0
    assert manifest.warnings == ()

    manifest_payload = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["source"]["format"] == "binance_data_vision_usdm_daily_book_depth_zip"
    assert len(manifest_payload["features_sha256"]) == 64

    depth_rows = pq.read_table(manifest.cleaned_path).to_pylist()
    assert depth_rows[0]["symbol"] == "BTCUSDT"
    assert depth_rows[0]["side"] == "bid"
    assert depth_rows[0]["distance_pct"] == 5
    assert depth_rows[-1]["side"] == "ask"

    feature_rows = pq.read_table(manifest.features_path).to_pylist()
    assert feature_rows[0]["bd_band_count"] == 10
    assert feature_rows[0]["bd_bid_notional_1pct"] == 10.0
    assert feature_rows[0]["bd_ask_notional_1pct"] == 10.0
    assert feature_rows[0]["bd_imbalance_1pct"] == pytest.approx(0.0)
    assert feature_rows[1]["bd_imbalance_1pct"] == pytest.approx(1 / 3)


def test_generate_binance_book_depth_dataset_rejects_duplicate_band(
    tmp_path: Path,
) -> None:
    duplicate_rows = [
        "2026-01-01 00:00:01,-1,1,10",
        "2026-01-01 00:00:01,-1,1,10",
    ]
    with pytest.raises(BinanceBookDepthError, match="duplicate book-depth row"):
        generate_binance_book_depth_dataset(
            BinanceBookDepthDatasetConfig(
                symbols=("BTCUSDT",),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 2),
                output_dir=tmp_path,
                dataset_name="duplicate_book_depth",
                generator_version="unit.v1",
            ),
            fetch_zip=_fake_fetch_zip({"BTCUSDT": [duplicate_rows]}),
        )


def test_generate_binance_book_depth_dataset_can_record_missing_files(
    tmp_path: Path,
) -> None:
    manifest = generate_binance_book_depth_dataset(
        BinanceBookDepthDatasetConfig(
            symbols=("BTCUSDT", "ETHUSDT"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            output_dir=tmp_path,
            dataset_name="missing_book_depth",
            generator_version="unit.v1",
            allow_missing_files=True,
        ),
        fetch_zip=_fake_fetch_zip({"BTCUSDT": [_rows_for_timestamp("2026-01-01 00:00:01")]}),
    )

    assert manifest.row_count == 10
    assert manifest.source_file_count == 1
    assert manifest.missing_file_count == 1
    assert manifest.symbols == ("BTCUSDT",)
    assert "missing book-depth file:" in manifest.warnings[0]


def test_write_binance_book_depth_coverage_report(tmp_path: Path) -> None:
    report = write_binance_book_depth_coverage_report(
        BinanceBookDepthCoverageConfig(
            symbols=("BTCUSDT", "ETHUSDT"),
            windows=(("unit", date(2026, 1, 1), date(2026, 1, 3)),),
            output_json_path=tmp_path / "coverage.json",
            output_markdown_path=tmp_path / "coverage.md",
            max_workers=2,
        ),
        fetch_head=_fake_fetch_head(
            {
                "BTCUSDT-bookDepth-2026-01-01.zip": 100,
                "BTCUSDT-bookDepth-2026-01-02.zip": 200,
                "ETHUSDT-bookDepth-2026-01-01.zip": 300,
            }
        ),
    )

    assert report["summary"]["expected_files"] == 4
    assert report["summary"]["available_files"] == 3
    assert report["summary"]["missing_files"] == 1
    assert report["summary"]["estimated_compressed_bytes"] == 600
    assert len(report["missing_files"]) == 1

    markdown = (tmp_path / "coverage.md").read_text(encoding="utf-8")
    assert "Available files" in markdown
    assert "ETHUSDT" in markdown


def _rows_for_timestamp(timestamp: str, *, bid_multiplier: int = 1) -> list[str]:
    rows = []
    for band in BANDS:
        notional = abs(band) * 10
        if band < 0:
            notional *= bid_multiplier
        rows.append(f"{timestamp},{band},{abs(band)},{notional}")
    return rows


def _fake_fetch_zip(rows_by_symbol: dict[str, list[list[str]]]):
    def fetch(url: str) -> bytes:
        for symbol, row_groups in rows_by_symbol.items():
            if f"/{symbol}/" in url:
                return _zip_csv(
                    f"{Path(url).stem}.csv",
                    [row for rows in row_groups for row in rows],
                )
        raise FileNotFoundError(url)

    return fetch


def _fake_fetch_head(content_lengths_by_file: dict[str, int]):
    def fetch(url: str) -> tuple[int, int | None]:
        file_name = Path(url).name
        if file_name not in content_lengths_by_file:
            raise FileNotFoundError(url)
        return 200, content_lengths_by_file[file_name]

    return fetch


def _zip_csv(csv_name: str, rows: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(csv_name, CSV_HEADER + "\n".join(rows) + "\n")
    return buffer.getvalue()
