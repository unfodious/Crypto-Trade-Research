import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.binance_liquidations import (
    BinanceLiquidationSnapshotConfig,
    BinanceLiquidationSnapshotError,
    generate_binance_liquidation_snapshot_async,
)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _force_order_message(
    *,
    symbol: str,
    side: str,
    event_time: datetime,
    quantity: str = "2.5",
    average_price: str = "100.5",
) -> dict[str, object]:
    return {
        "e": "forceOrder",
        "E": _ms(event_time),
        "o": {
            "s": symbol,
            "S": side,
            "o": "LIMIT",
            "f": "IOC",
            "q": quantity,
            "p": "100.0",
            "ap": average_price,
            "X": "FILLED",
            "l": quantity,
            "z": quantity,
            "T": _ms(event_time),
        },
    }


def test_generate_binance_liquidation_snapshot_writes_manifest_and_run_summary(
    tmp_path: Path,
) -> None:
    generated_at = datetime(2026, 5, 27, 10, 45, tzinfo=UTC)
    event_time = datetime(2026, 5, 27, 10, 44, tzinfo=UTC)
    manifest = asyncio.run(
        generate_binance_liquidation_snapshot_async(
            BinanceLiquidationSnapshotConfig(
                symbols=("BTCUSDT", "ETHUSDT"),
                output_dir=tmp_path,
                dataset_prefix="unit_binance_liquidations",
                generator_version="unit.liquidations.v1",
                generated_at=generated_at,
                capture_seconds=1,
            ),
            messages=[
                json.dumps(
                    _force_order_message(symbol="BTCUSDT", side="SELL", event_time=event_time)
                ),
                {
                    "stream": "!forceOrder@arr",
                    "data": _force_order_message(
                        symbol="ETHUSDT",
                        side="BUY",
                        event_time=event_time,
                    ),
                },
                json.dumps(
                    _force_order_message(symbol="DOGEUSDT", side="SELL", event_time=event_time)
                ),
            ],
        )
    )

    assert manifest.row_count == 2
    assert manifest.event_count_total == 3
    assert manifest.event_count_filtered_out == 1
    assert manifest.symbols == ("BTCUSDT", "ETHUSDT")
    assert manifest.liquidations_path.exists()
    assert manifest.manifest_path.exists()
    assert len(manifest.liquidations_sha256) == 64

    rows = pq.read_table(manifest.liquidations_path).to_pylist()
    btc_row = next(row for row in rows if row["symbol"] == "BTCUSDT")
    eth_row = next(row for row in rows if row["symbol"] == "ETHUSDT")
    assert btc_row["event_time"] == event_time
    assert btc_row["source_available_at"] == generated_at
    assert btc_row["side"] == "SELL"
    assert btc_row["liquidation_direction"] == "long_liquidation"
    assert btc_row["notional"] == pytest.approx(251.25)
    assert eth_row["side"] == "BUY"
    assert eth_row["liquidation_direction"] == "short_liquidation"

    manifest_json = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert manifest_json["schema_version"] == "research.binance_futures_liquidation_snapshot.v1"
    assert manifest_json["source"]["history_limit_note"]
    assert manifest_json["liquidations_path"] == str(manifest.liquidations_path)

    run_summary = json.loads(
        (tmp_path / "unit_binance_liquidations" / "liquidation_run.json").read_text(
            encoding="utf-8"
        )
    )
    assert run_summary["schema_version"] == "research.binance_futures_liquidation_run.v1"
    assert run_summary["latest_manifest_path"] == str(manifest.manifest_path)
    assert run_summary["row_count"] == 2
    assert run_summary["event_count_total"] == 3
    assert run_summary["event_count_filtered_out"] == 1


def test_generate_binance_liquidation_snapshot_preserves_empty_windows(
    tmp_path: Path,
) -> None:
    manifest = asyncio.run(
        generate_binance_liquidation_snapshot_async(
            BinanceLiquidationSnapshotConfig(
                symbols=("BTCUSDT",),
                output_dir=tmp_path,
                dataset_prefix="unit_binance_liquidations",
                generator_version="unit.liquidations.v1",
                generated_at=datetime(2026, 5, 27, 10, 45, tzinfo=UTC),
                capture_seconds=1,
            ),
            messages=[],
        )
    )

    assert manifest.row_count == 0
    assert manifest.event_count_total == 0
    assert manifest.liquidations_path.exists()
    assert pq.read_table(manifest.liquidations_path).num_rows == 0


def test_generate_binance_liquidation_snapshot_warns_on_malformed_message(
    tmp_path: Path,
) -> None:
    manifest = asyncio.run(
        generate_binance_liquidation_snapshot_async(
            BinanceLiquidationSnapshotConfig(
                symbols=("BTCUSDT",),
                output_dir=tmp_path,
                dataset_prefix="unit_binance_liquidations",
                generator_version="unit.liquidations.v1",
                generated_at=datetime(2026, 5, 27, 10, 45, tzinfo=UTC),
                capture_seconds=1,
            ),
            messages=["not-json"],
        )
    )

    assert manifest.row_count == 0
    assert len(manifest.warnings) == 1
    assert "liquidation message failed" in manifest.warnings[0]


def test_binance_liquidation_snapshot_rejects_invalid_config(tmp_path: Path) -> None:
    with pytest.raises(BinanceLiquidationSnapshotError, match="capture_seconds"):
        asyncio.run(
            generate_binance_liquidation_snapshot_async(
                BinanceLiquidationSnapshotConfig(
                    symbols=("BTCUSDT",),
                    output_dir=tmp_path,
                    dataset_prefix="unit_binance_liquidations",
                    generator_version="unit.liquidations.v1",
                    capture_seconds=0,
                ),
                messages=[],
            )
        )
