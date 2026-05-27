import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.hyperliquid_whales import (
    HyperliquidWhaleDatasetError,
    HyperliquidWhaleSnapshotConfig,
    WatchedWallet,
    generate_hyperliquid_whale_snapshot,
)

WALLET = "0xf3f496c9486be5924a93d67e98298733bb47057c"


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def test_generate_hyperliquid_whale_snapshot_writes_positions_and_fills(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fetch_info(payload: dict[str, object], base_url: str) -> object:
        calls.append({**payload, "base_url": base_url})
        if payload["type"] == "clearinghouseState":
            return {
                "assetPositions": [
                    {
                        "position": {
                            "coin": "ETH",
                            "szi": "10.5",
                            "positionValue": "21000.0",
                            "entryPx": "1900.0",
                            "markPx": "2000.0",
                            "unrealizedPnl": "1050.0",
                            "returnOnEquity": "0.5",
                            "leverage": {"type": "cross", "value": 20},
                            "liquidationPx": "1800.0",
                        }
                    }
                ]
            }
        return [
            {
                "coin": "ETH",
                "px": "2000.0",
                "sz": "10.5",
                "side": "B",
                "time": _ms(datetime(2026, 5, 27, 10, tzinfo=UTC)),
                "dir": "Open Long",
                "closedPnl": "0.0",
                "hash": "0xabc",
                "oid": 123,
                "crossed": True,
                "fee": "1.5",
                "tid": 456,
                "feeToken": "USDC",
            }
        ]

    manifest = generate_hyperliquid_whale_snapshot(
        HyperliquidWhaleSnapshotConfig(
            wallets=(WatchedWallet(address=WALLET, alias="eth_whale"),),
            output_dir=tmp_path,
            dataset_name="unit_hyperliquid_whales",
            generator_version="unit.hyperliquid.v1",
            generated_at=datetime(2026, 5, 27, 11, tzinfo=UTC),
        ),
        fetch_info=fetch_info,
    )

    assert manifest.position_count == 1
    assert manifest.fill_count == 1
    assert manifest.wallets == (WALLET,)
    assert manifest.raw_path.exists()
    assert manifest.positions_path.exists()
    assert manifest.fills_path.exists()
    assert len(manifest.positions_sha256) == 64

    positions = pq.read_table(manifest.positions_path).to_pylist()
    assert positions[0]["wallet_address"] == WALLET
    assert positions[0]["symbol"] == "ETH"
    assert positions[0]["side"] == "long"
    assert positions[0]["notional_usd"] == pytest.approx(21000.0)
    assert positions[0]["leverage_type"] == "cross"
    assert positions[0]["leverage_value"] == pytest.approx(20.0)

    fills = pq.read_table(manifest.fills_path).to_pylist()
    assert fills[0]["symbol"] == "ETH"
    assert fills[0]["side"] == "buy"
    assert fills[0]["notional_usd"] == pytest.approx(21000.0)

    manifest_json = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert manifest_json["schema_version"] == "research.hyperliquid_whale_snapshot.v1"
    assert manifest_json["source"]["format"] == "hyperliquid_info_rest"
    assert [call["type"] for call in calls] == ["clearinghouseState", "userFills"]


def test_generate_hyperliquid_whale_snapshot_records_inactive_wallet_warning(
    tmp_path: Path,
) -> None:
    def fetch_info(payload: dict[str, object], base_url: str) -> object:
        if payload["type"] == "clearinghouseState":
            return {"assetPositions": []}
        return []

    manifest = generate_hyperliquid_whale_snapshot(
        HyperliquidWhaleSnapshotConfig(
            wallets=(WatchedWallet(address=WALLET),),
            output_dir=tmp_path,
            dataset_name="inactive_wallet",
            generator_version="unit.hyperliquid.v1",
        ),
        fetch_info=fetch_info,
    )

    assert manifest.position_count == 0
    assert manifest.fill_count == 0
    assert manifest.warnings == (
        f"{WALLET} has no open Hyperliquid perp positions at snapshot time",
    )


def test_generate_hyperliquid_whale_snapshot_rejects_bad_wallet(tmp_path: Path) -> None:
    with pytest.raises(HyperliquidWhaleDatasetError, match="invalid EVM wallet address"):
        generate_hyperliquid_whale_snapshot(
            HyperliquidWhaleSnapshotConfig(
                wallets=(WatchedWallet(address="not-an-address"),),
                output_dir=tmp_path,
                dataset_name="bad_wallet",
                generator_version="unit.hyperliquid.v1",
            ),
            fetch_info=lambda payload, base_url: {},
        )
