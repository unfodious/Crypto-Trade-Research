from datetime import UTC, datetime, timedelta
from pathlib import Path

from crypto_trade_research.data.hyperliquid_watchlist import (
    HyperliquidWatchlistRunConfig,
    HyperliquidWatchlistThresholds,
    run_hyperliquid_watchlist,
)
from crypto_trade_research.data.hyperliquid_whales import WatchedWallet

WALLET = "0xf3f496c9486be5924a93d67e98298733bb47057c"


def test_run_hyperliquid_watchlist_writes_run_manifest_and_alerts(tmp_path: Path) -> None:
    states = [
        {
            "assetPositions": [
                {
                    "position": {
                        "coin": "ETH",
                        "szi": "100",
                        "positionValue": "6000000",
                        "entryPx": "1900",
                        "markPx": "2000",
                        "unrealizedPnl": "1000",
                        "returnOnEquity": "0.1",
                        "leverage": {"type": "cross", "value": 20},
                        "liquidationPx": "1960",
                    }
                }
            ]
        },
        {
            "assetPositions": [
                {
                    "position": {
                        "coin": "ETH",
                        "szi": "125",
                        "positionValue": "7500000",
                        "entryPx": "1900",
                        "markPx": "2000",
                        "unrealizedPnl": "1500",
                        "returnOnEquity": "0.1",
                        "leverage": {"type": "cross", "value": 20},
                        "liquidationPx": "1960",
                    }
                }
            ]
        },
    ]
    calls: list[dict[str, object]] = []
    state_index = 0

    def fetch_info(payload: dict[str, object], base_url: str) -> object:
        nonlocal state_index
        calls.append(payload)
        if payload["type"] == "clearinghouseState":
            state = states[state_index]
            state_index += 1
            return state
        return []

    base_time = datetime(2026, 5, 27, 12, tzinfo=UTC)
    times = iter((base_time, base_time + timedelta(minutes=1)))
    result = run_hyperliquid_watchlist(
        HyperliquidWatchlistRunConfig(
            wallets=(WatchedWallet(address=WALLET, alias="eth_whale"),),
            output_dir=tmp_path,
            dataset_prefix="unit_watchlist",
            generator_version="unit.watchlist.v1",
            thresholds=HyperliquidWatchlistThresholds(
                min_position_notional_usd=5_000_000,
                min_leverage=10,
                max_liquidation_distance_pct=0.03,
                min_notional_delta_usd=1_000_000,
            ),
            iterations=2,
            poll_interval_seconds=0,
            include_fills=True,
        ),
        fetch_info=fetch_info,
        clock=lambda: next(times),
    )

    assert result["iterations"] == 2
    assert Path(str(result["run_path"])).exists()
    assert len(result["snapshots"]) == 2
    assert result["snapshots"][0]["position_count"] == 1
    assert result["alert_count"] == 6
    assert {alert["alert_type"] for alert in result["alerts"]} == {
        "large_leveraged_position",
        "near_liquidation",
        "position_notional_delta",
    }
    assert result["alerts"][-1]["notional_delta_usd"] == 1_500_000
    assert [call["type"] for call in calls] == [
        "clearinghouseState",
        "userFills",
        "clearinghouseState",
        "userFillsByTime",
    ]
    assert "startTime" in calls[-1]
    assert "endTime" in calls[-1]


def test_watchlist_config_from_dict_parses_thresholds(tmp_path: Path) -> None:
    config = HyperliquidWatchlistRunConfig.from_dict(
        {
            "wallets": [{"address": WALLET, "alias": "note"}],
            "output_dir": str(tmp_path),
            "dataset_prefix": "unit",
            "generator_version": "unit.v1",
            "iterations": 3,
            "poll_interval_seconds": 5,
            "fills_start_time": "2026-05-27T00:00:00Z",
            "include_fills": False,
            "thresholds": {
                "min_position_notional_usd": 123,
                "min_leverage": 4,
                "max_liquidation_distance_pct": 0.02,
                "min_notional_delta_usd": 99,
            },
        }
    )

    assert config.wallets[0].alias == "note"
    assert config.iterations == 3
    assert config.poll_interval_seconds == 5
    assert config.fills_start_time == datetime(2026, 5, 27, tzinfo=UTC)
    assert not config.include_fills
    assert config.thresholds.min_position_notional_usd == 123
    assert config.thresholds.min_leverage == 4
