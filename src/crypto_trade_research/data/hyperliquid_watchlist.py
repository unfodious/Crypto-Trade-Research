"""Forward watchlist runner for Hyperliquid whale research snapshots."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from crypto_trade_research.data.hyperliquid_whales import (
    HYPERLIQUID_INFO_URL,
    HyperliquidWhaleSnapshotConfig,
    InfoFetcher,
    WatchedWallet,
    generate_hyperliquid_whale_snapshot,
)

SCHEMA_VERSION = "research.hyperliquid_whale_watchlist_run.v1"
GENERATOR_NAME = "crypto_trade_research.hyperliquid_whale_watchlist"


class HyperliquidWatchlistError(ValueError):
    """Raised when the Hyperliquid watchlist runner configuration is invalid."""


@dataclass(frozen=True, slots=True)
class HyperliquidWatchlistThresholds:
    min_position_notional_usd: float = 5_000_000.0
    min_leverage: float = 10.0
    max_liquidation_distance_pct: float = 0.03
    min_notional_delta_usd: float = 1_000_000.0


@dataclass(frozen=True, slots=True)
class HyperliquidWatchlistRunConfig:
    wallets: tuple[WatchedWallet, ...]
    output_dir: Path
    dataset_prefix: str
    generator_version: str
    thresholds: HyperliquidWatchlistThresholds
    iterations: int = 1
    poll_interval_seconds: float = 60.0
    venue: str = "hyperliquid"
    base_url: str = HYPERLIQUID_INFO_URL
    fills_start_time: datetime | None = None
    include_fills: bool = True
    aggregate_fills_by_time: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> HyperliquidWatchlistRunConfig:
        thresholds = dict(payload.get("thresholds", {}))
        return cls(
            wallets=tuple(_wallet_from_payload(item) for item in payload.get("wallets", ())),
            output_dir=Path(str(payload["output_dir"])),
            dataset_prefix=str(payload["dataset_prefix"]),
            generator_version=str(payload["generator_version"]),
            thresholds=HyperliquidWatchlistThresholds(
                min_position_notional_usd=float(
                    thresholds.get("min_position_notional_usd", 5_000_000.0)
                ),
                min_leverage=float(thresholds.get("min_leverage", 10.0)),
                max_liquidation_distance_pct=float(
                    thresholds.get("max_liquidation_distance_pct", 0.03)
                ),
                min_notional_delta_usd=float(thresholds.get("min_notional_delta_usd", 1_000_000.0)),
            ),
            iterations=int(payload.get("iterations", 1)),
            poll_interval_seconds=float(payload.get("poll_interval_seconds", 60.0)),
            venue=str(payload.get("venue", "hyperliquid")),
            base_url=str(payload.get("base_url", HYPERLIQUID_INFO_URL)),
            fills_start_time=_parse_timestamp_optional(payload.get("fills_start_time")),
            include_fills=bool(payload.get("include_fills", True)),
            aggregate_fills_by_time=bool(payload.get("aggregate_fills_by_time", True)),
        )

    @classmethod
    def from_path(cls, path: Path) -> HyperliquidWatchlistRunConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


SleepFn = Callable[[float], None]


def run_hyperliquid_watchlist(
    config: HyperliquidWatchlistRunConfig,
    *,
    fetch_info: InfoFetcher | None = None,
    sleep_fn: SleepFn = time.sleep,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Run one or more watched-wallet polling iterations and write a run manifest."""

    _validate_config(config)
    now = clock or (lambda: datetime.now(UTC))
    previous_positions: dict[tuple[str, str, str], dict[str, object]] = {}
    snapshots: list[dict[str, object]] = []
    all_alerts: list[dict[str, object]] = []
    fills_start_time = config.fills_start_time

    for index in range(config.iterations):
        generated_at = now().astimezone(UTC)
        dataset_name = f"{config.dataset_prefix}_{_compact_timestamp(generated_at)}"
        manifest = generate_hyperliquid_whale_snapshot(
            HyperliquidWhaleSnapshotConfig(
                wallets=config.wallets,
                output_dir=config.output_dir,
                dataset_name=dataset_name,
                generator_version=config.generator_version,
                generated_at=generated_at,
                venue=config.venue,
                base_url=config.base_url,
                fills_start_time=fills_start_time,
                fills_end_time=generated_at if fills_start_time is not None else None,
                include_fills=config.include_fills,
                aggregate_fills_by_time=config.aggregate_fills_by_time,
            ),
            fetch_info=fetch_info,
        )
        positions = _load_positions(manifest.positions_path)
        alerts = _alerts_for_positions(
            positions,
            previous_positions,
            config.thresholds,
            generated_at=generated_at,
        )
        current_positions = _position_index(positions)
        snapshots.append(
            {
                "iteration": index + 1,
                "generated_at": _format_timestamp(generated_at),
                "dataset_name": dataset_name,
                "manifest_path": str(manifest.manifest_path),
                "position_count": manifest.position_count,
                "fill_count": manifest.fill_count,
                "warning_count": len(manifest.warnings),
                "warnings": list(manifest.warnings),
                "alert_count": len(alerts),
                "alerts": alerts,
            }
        )
        all_alerts.extend(alerts)
        previous_positions = current_positions
        fills_start_time = generated_at
        if index + 1 < config.iterations and config.poll_interval_seconds > 0:
            sleep_fn(config.poll_interval_seconds)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generator_name": GENERATOR_NAME,
        "generator_version": config.generator_version,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "dataset_prefix": config.dataset_prefix,
        "wallets": [asdict(wallet) for wallet in config.wallets],
        "thresholds": asdict(config.thresholds),
        "iterations": config.iterations,
        "poll_interval_seconds": config.poll_interval_seconds,
        "fills_start_time": _format_timestamp(config.fills_start_time)
        if config.fills_start_time is not None
        else None,
        "include_fills": config.include_fills,
        "snapshots": snapshots,
        "alert_count": len(all_alerts),
        "alerts": all_alerts,
        "notes": "Research-only watchlist run. No orders are submitted or modified.",
    }
    run_dir = config.output_dir / config.dataset_prefix
    run_path = run_dir / "watchlist_run.json"
    _write_json(run_path, payload)
    return {**payload, "run_path": str(run_path)}


def _alerts_for_positions(
    positions: list[dict[str, object]],
    previous_positions: dict[tuple[str, str, str], dict[str, object]],
    thresholds: HyperliquidWatchlistThresholds,
    *,
    generated_at: datetime,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for position in positions:
        key = _position_key(position)
        notional = _float(position.get("notional_usd"))
        leverage = _float(position.get("leverage_value"))
        mark_price = _float(position.get("mark_price"))
        liquidation_price = _float(position.get("liquidation_price"))
        previous_notional = _float(previous_positions.get(key, {}).get("notional_usd"))
        notional_delta = notional - previous_notional
        if notional >= thresholds.min_position_notional_usd and leverage >= thresholds.min_leverage:
            alerts.append(
                _alert(
                    "large_leveraged_position",
                    position,
                    generated_at,
                    notional_delta=notional_delta,
                    liquidation_distance_pct=_liquidation_distance_pct(
                        mark_price,
                        liquidation_price,
                    ),
                )
            )
        liquidation_distance = _liquidation_distance_pct(mark_price, liquidation_price)
        if (
            liquidation_distance is not None
            and liquidation_distance <= thresholds.max_liquidation_distance_pct
        ):
            alerts.append(
                _alert(
                    "near_liquidation",
                    position,
                    generated_at,
                    notional_delta=notional_delta,
                    liquidation_distance_pct=liquidation_distance,
                )
            )
        if abs(notional_delta) >= thresholds.min_notional_delta_usd:
            alerts.append(
                _alert(
                    "position_notional_delta",
                    position,
                    generated_at,
                    notional_delta=notional_delta,
                    liquidation_distance_pct=liquidation_distance,
                )
            )
    return alerts


def _alert(
    alert_type: str,
    position: dict[str, object],
    generated_at: datetime,
    *,
    notional_delta: float,
    liquidation_distance_pct: float | None,
) -> dict[str, object]:
    return {
        "alert_type": alert_type,
        "source_available_at": _format_timestamp(generated_at),
        "wallet_address": str(position.get("wallet_address", "")),
        "symbol": str(position.get("symbol", "")),
        "side": str(position.get("side", "")),
        "notional_usd": _float(position.get("notional_usd")),
        "notional_delta_usd": notional_delta,
        "leverage_value": _float(position.get("leverage_value")),
        "mark_price": _optional_float(position.get("mark_price")),
        "liquidation_price": _optional_float(position.get("liquidation_price")),
        "liquidation_distance_pct": liquidation_distance_pct,
    }


def _load_positions(path: Path) -> list[dict[str, object]]:
    return [dict(row) for row in pq.read_table(path).to_pylist()]


def _position_index(
    positions: list[dict[str, object]],
) -> dict[tuple[str, str, str], dict[str, object]]:
    return {_position_key(position): position for position in positions}


def _position_key(position: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(position.get("wallet_address", "")),
        str(position.get("symbol", "")),
        str(position.get("side", "")),
    )


def _liquidation_distance_pct(
    mark_price: float,
    liquidation_price: float,
) -> float | None:
    if mark_price <= 0 or liquidation_price <= 0:
        return None
    return abs(mark_price - liquidation_price) / mark_price


def _wallet_from_payload(payload: object) -> WatchedWallet:
    item = dict(payload)
    return WatchedWallet(
        address=str(item["address"]),
        alias=str(item["alias"]) if item.get("alias") is not None else None,
    )


def _validate_config(config: HyperliquidWatchlistRunConfig) -> None:
    if not config.wallets:
        raise HyperliquidWatchlistError("watchlist must include at least one wallet")
    if config.iterations <= 0:
        raise HyperliquidWatchlistError("iterations must be positive")
    if config.poll_interval_seconds < 0:
        raise HyperliquidWatchlistError("poll_interval_seconds must be non-negative")
    if config.thresholds.min_position_notional_usd < 0:
        raise HyperliquidWatchlistError("min_position_notional_usd must be non-negative")
    if config.thresholds.min_leverage < 0:
        raise HyperliquidWatchlistError("min_leverage must be non-negative")
    if config.thresholds.max_liquidation_distance_pct < 0:
        raise HyperliquidWatchlistError("max_liquidation_distance_pct must be non-negative")
    if config.thresholds.min_notional_delta_usd < 0:
        raise HyperliquidWatchlistError("min_notional_delta_usd must be non-negative")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _float(value: object) -> float:
    return float(value) if value is not None else 0.0


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _compact_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp_optional(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--poll-interval-seconds", type=float)
    parser.add_argument("--fills-start-time")
    parser.add_argument("--skip-fills", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config_payload = json.loads(args.config.read_text(encoding="utf-8"))
    if args.iterations is not None:
        config_payload["iterations"] = args.iterations
    if args.poll_interval_seconds is not None:
        config_payload["poll_interval_seconds"] = args.poll_interval_seconds
    if args.fills_start_time is not None:
        config_payload["fills_start_time"] = args.fills_start_time
    if args.skip_fills:
        config_payload["include_fills"] = False
    result = run_hyperliquid_watchlist(HyperliquidWatchlistRunConfig.from_dict(config_payload))
    print(result["run_path"])


if __name__ == "__main__":
    main()
