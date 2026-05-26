import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.funding import (
    FundingRateDatasetConfig,
    FundingRateDatasetError,
    generate_funding_rate_dataset,
)


def _ts(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, tzinfo=UTC)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def test_generate_funding_rate_dataset_paginates_and_writes_manifest(tmp_path: Path) -> None:
    calls = []

    def fetch_page(
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        base_url: str,
    ) -> list[dict[str, object]]:
        calls.append((symbol, start_time, end_time, limit, base_url))
        rows = {
            "BTCUSDT": [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.00010000",
                    "fundingTime": _ms(_ts(0)),
                    "markPrice": "100.0",
                },
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "-0.00020000",
                    "fundingTime": _ms(_ts(8)),
                    "markPrice": "101.0",
                },
            ],
            "ETHUSDT": [
                {
                    "symbol": "ETHUSDT",
                    "fundingRate": "0.00030000",
                    "fundingTime": _ms(_ts(0)),
                    "markPrice": "50.0",
                }
            ],
        }[symbol]
        return [row for row in rows if _ms(start_time) <= int(row["fundingTime"]) <= _ms(end_time)]

    manifest = generate_funding_rate_dataset(
        FundingRateDatasetConfig(
            symbols=("BTCUSDT", "ETHUSDT"),
            start_time=_ts(0),
            end_time=_ts(8),
            output_dir=tmp_path,
            dataset_name="unit_funding_dataset",
            generator_version="unit.funding.v1",
            generated_at=datetime(2026, 1, 2, tzinfo=UTC),
            request_sleep_seconds=0.0,
        ),
        fetch_page=fetch_page,
    )

    assert manifest.row_count == 3
    assert manifest.symbols == ("BTCUSDT", "ETHUSDT")
    assert manifest.min_funding_time == "2026-01-01T00:00:00Z"
    assert manifest.max_funding_time == "2026-01-01T08:00:00Z"
    assert manifest.raw_path.exists()
    assert manifest.cleaned_path.exists()
    assert manifest.manifest_path.exists()
    assert len(manifest.raw_sha256) == 64
    assert len(manifest.cleaned_sha256) == 64

    clean_rows = pq.read_table(manifest.cleaned_path).to_pylist()
    assert [row["symbol"] for row in clean_rows] == ["BTCUSDT", "BTCUSDT", "ETHUSDT"]
    assert clean_rows[0]["funding_rate"] == pytest.approx(0.0001)
    assert clean_rows[0]["source_available_at"] == clean_rows[0]["funding_time"]

    manifest_json = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert manifest_json["schema_version"] == "research.funding_rate.v1"
    assert manifest_json["source"]["format"] == "binance_usdm_funding_rate_rest"
    assert manifest_json["source"]["limit"] == 1000
    assert calls[0][0] == "BTCUSDT"


def test_generate_funding_rate_dataset_rejects_duplicate_rows(tmp_path: Path) -> None:
    def fetch_page(
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        limit: int,
        base_url: str,
    ) -> list[dict[str, object]]:
        return [
            {
                "symbol": symbol,
                "fundingRate": "0.00010000",
                "fundingTime": _ms(_ts(0)),
                "markPrice": "100.0",
            },
            {
                "symbol": symbol,
                "fundingRate": "0.00010000",
                "fundingTime": _ms(_ts(0)),
                "markPrice": "100.0",
            },
        ]

    with pytest.raises(FundingRateDatasetError, match="duplicate funding row"):
        generate_funding_rate_dataset(
            FundingRateDatasetConfig(
                symbols=("BTCUSDT",),
                start_time=_ts(0),
                end_time=_ts(8),
                output_dir=tmp_path,
                dataset_name="unit_funding_dataset",
                generator_version="unit.funding.v1",
                request_sleep_seconds=0.0,
            ),
            fetch_page=fetch_page,
        )
