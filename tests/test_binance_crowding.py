import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.binance_crowding import (
    BinanceCrowdingSnapshotConfig,
    BinanceCrowdingSnapshotError,
    generate_binance_crowding_snapshot,
)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def test_generate_binance_crowding_snapshot_writes_manifest_and_run_summary(
    tmp_path: Path,
) -> None:
    generated_at = datetime(2026, 5, 27, 10, 45, tzinfo=UTC)
    event_time = datetime(2026, 5, 27, 10, 40, tzinfo=UTC)
    calls: list[tuple[str, str]] = []

    def fetch_open_interest(symbol: str, base_url: str) -> dict[str, object]:
        calls.append(("oi", symbol))
        return {"symbol": symbol, "openInterest": "123.45", "time": _ms(event_time)}

    def fetch_open_interest_hist(
        symbol: str,
        period: str,
        limit: int,
        base_url: str,
    ) -> list[dict[str, object]]:
        calls.append(("oi_hist", f"{symbol}:{period}:{limit}"))
        return [
            {
                "symbol": symbol,
                "sumOpenInterest": "123.45",
                "sumOpenInterestValue": "67890.12",
                "CMCCirculatingSupply": "456.7",
                "timestamp": _ms(event_time),
            }
        ]

    def fetch_global_long_short(
        symbol: str,
        period: str,
        limit: int,
        base_url: str,
    ) -> list[dict[str, object]]:
        calls.append(("long_short", f"{symbol}:{period}:{limit}"))
        return [
            {
                "symbol": symbol,
                "longShortRatio": "1.50",
                "longAccount": "0.60",
                "shortAccount": "0.40",
                "timestamp": _ms(event_time),
            }
        ]

    manifest = generate_binance_crowding_snapshot(
        BinanceCrowdingSnapshotConfig(
            symbols=("BTCUSDT", "ETHUSDT"),
            output_dir=tmp_path,
            dataset_prefix="unit_binance_crowding",
            generator_version="unit.crowding.v1",
            generated_at=generated_at,
            period="5m",
            limit=1,
            request_sleep_seconds=0,
        ),
        fetch_open_interest=fetch_open_interest,
        fetch_open_interest_hist=fetch_open_interest_hist,
        fetch_global_long_short=fetch_global_long_short,
    )

    assert manifest.row_count == 6
    assert manifest.symbols == ("BTCUSDT", "ETHUSDT")
    assert manifest.current_open_interest_path.exists()
    assert manifest.open_interest_hist_path.exists()
    assert manifest.global_long_short_path.exists()
    assert manifest.manifest_path.exists()
    assert len(manifest.current_open_interest_sha256) == 64
    assert len(manifest.open_interest_hist_sha256) == 64
    assert len(manifest.global_long_short_sha256) == 64

    oi_rows = pq.read_table(manifest.current_open_interest_path).to_pylist()
    assert oi_rows[0]["source_available_at"] == generated_at
    assert oi_rows[0]["event_time"] == event_time
    assert oi_rows[0]["open_interest"] == pytest.approx(123.45)

    long_short_rows = pq.read_table(manifest.global_long_short_path).to_pylist()
    assert long_short_rows[0]["long_short_ratio"] == pytest.approx(1.5)
    assert long_short_rows[0]["period"] == "5m"

    manifest_json = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert manifest_json["schema_version"] == "research.binance_futures_crowding_snapshot.v1"
    assert manifest_json["source"]["history_limit_note"]

    run_summary = json.loads(
        (tmp_path / "unit_binance_crowding" / "crowding_run.json").read_text(encoding="utf-8")
    )
    assert run_summary["latest_manifest_path"] == str(manifest.manifest_path)
    assert run_summary["row_count"] == 6
    assert calls[0] == ("oi", "BTCUSDT")


def test_generate_binance_crowding_snapshot_preserves_partial_source_warnings(
    tmp_path: Path,
) -> None:
    generated_at = datetime(2026, 5, 27, 10, 45, tzinfo=UTC)
    event_time = datetime(2026, 5, 27, 10, 40, tzinfo=UTC)

    def fetch_open_interest(symbol: str, base_url: str) -> dict[str, object]:
        return {"symbol": symbol, "openInterest": "123.45", "time": _ms(event_time)}

    def fail_series(
        symbol: str,
        period: str,
        limit: int,
        base_url: str,
    ) -> list[dict[str, object]]:
        raise RuntimeError("rate limited")

    manifest = generate_binance_crowding_snapshot(
        BinanceCrowdingSnapshotConfig(
            symbols=("BTCUSDT",),
            output_dir=tmp_path,
            dataset_prefix="unit_binance_crowding",
            generator_version="unit.crowding.v1",
            generated_at=generated_at,
            request_sleep_seconds=0,
        ),
        fetch_open_interest=fetch_open_interest,
        fetch_open_interest_hist=fail_series,
        fetch_global_long_short=fail_series,
    )

    assert manifest.row_count == 1
    assert len(manifest.warnings) == 2
    assert "rate limited" in manifest.warnings[0]


def test_binance_crowding_snapshot_rejects_empty_source(tmp_path: Path) -> None:
    def fail_open_interest(symbol: str, base_url: str) -> dict[str, object]:
        raise RuntimeError("offline")

    def fail_series(
        symbol: str,
        period: str,
        limit: int,
        base_url: str,
    ) -> list[dict[str, object]]:
        raise RuntimeError("offline")

    with pytest.raises(BinanceCrowdingSnapshotError, match="all Binance crowding sources"):
        generate_binance_crowding_snapshot(
            BinanceCrowdingSnapshotConfig(
                symbols=("BTCUSDT",),
                output_dir=tmp_path,
                dataset_prefix="unit_binance_crowding",
                generator_version="unit.crowding.v1",
                request_sleep_seconds=0,
            ),
            fetch_open_interest=fail_open_interest,
            fetch_open_interest_hist=fail_series,
            fetch_global_long_short=fail_series,
        )
