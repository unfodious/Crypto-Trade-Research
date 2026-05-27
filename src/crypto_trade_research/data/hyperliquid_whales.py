"""Hyperliquid watched-wallet snapshot ingestion for research-only signals."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "research.hyperliquid_whale_snapshot.v1"
GENERATOR_NAME = "crypto_trade_research.hyperliquid_whale_snapshot"
HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"

WHALE_POSITION_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "venue",
    "wallet_address",
    "source_available_at",
    "symbol",
    "side",
    "position_size",
    "notional_usd",
    "entry_price",
    "mark_price",
    "unrealized_pnl_usd",
    "return_on_equity",
    "leverage_type",
    "leverage_value",
    "liquidation_price",
)

WHALE_FILL_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "venue",
    "wallet_address",
    "source_available_at",
    "fill_time",
    "symbol",
    "side",
    "direction",
    "price",
    "size",
    "notional_usd",
    "closed_pnl_usd",
    "fee",
    "fee_token",
    "order_id",
    "trade_id",
    "hash",
    "crossed",
)

InfoFetcher = Callable[[dict[str, object], str], object]


class HyperliquidWhaleDatasetError(ValueError):
    """Raised when Hyperliquid whale snapshot ingestion fails."""


@dataclass(frozen=True, slots=True)
class WatchedWallet:
    address: str
    alias: str | None = None


@dataclass(frozen=True, slots=True)
class HyperliquidWhaleSnapshotConfig:
    wallets: tuple[WatchedWallet, ...]
    output_dir: Path
    dataset_name: str
    generator_version: str
    generated_at: datetime | None = None
    venue: str = "hyperliquid"
    base_url: str = HYPERLIQUID_INFO_URL
    fills_start_time: datetime | None = None
    fills_end_time: datetime | None = None
    include_fills: bool = True
    aggregate_fills_by_time: bool = True


@dataclass(frozen=True, slots=True)
class HyperliquidWhaleSnapshotManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    wallet_count: int
    position_count: int
    fill_count: int
    wallets: tuple[str, ...]
    raw_path: Path
    positions_path: Path
    fills_path: Path
    manifest_path: Path
    raw_sha256: str
    positions_sha256: str
    fills_sha256: str
    warnings: tuple[str, ...]


def generate_hyperliquid_whale_snapshot(
    config: HyperliquidWhaleSnapshotConfig,
    *,
    fetch_info: InfoFetcher | None = None,
) -> HyperliquidWhaleSnapshotManifest:
    """Fetch current watched-wallet state and recent fills from Hyperliquid public API."""

    _validate_config(config)
    info_fetcher = fetch_info or _fetch_hyperliquid_info
    generated_at = config.generated_at or datetime.now(UTC)
    source_available_at = _format_timestamp(generated_at)
    raw_wallets: list[dict[str, object]] = []
    position_rows: list[dict[str, object]] = []
    fill_rows: list[dict[str, object]] = []
    warnings: list[str] = []

    for wallet in config.wallets:
        address = wallet.address.lower()
        state = _fetch_user_state(address, config, info_fetcher)
        fills = _fetch_user_fills(address, config, info_fetcher) if config.include_fills else []
        raw_wallets.append(
            {
                "address": address,
                "alias": wallet.alias,
                "state": state,
                "fills": fills,
                "source_available_at": source_available_at,
            }
        )
        position_rows.extend(
            _normalize_position_rows(
                state,
                wallet_address=address,
                source_available_at=source_available_at,
                venue=config.venue,
            )
        )
        fill_rows.extend(
            _normalize_fill_rows(
                fills,
                wallet_address=address,
                source_available_at=source_available_at,
                venue=config.venue,
            )
        )
        if not dict(state).get("assetPositions"):
            warnings.append(f"{address} has no open Hyperliquid perp positions at snapshot time")

    cleaned_positions = _validate_and_sort_positions(position_rows)
    cleaned_fills = _validate_and_sort_fills(fill_rows)
    dataset_dir = config.output_dir / config.dataset_name
    raw_path = dataset_dir / "raw" / "wallet_snapshots.json"
    positions_path = dataset_dir / "clean" / "positions.parquet"
    fills_path = dataset_dir / "clean" / "fills.parquet"
    manifest_path = dataset_dir / "manifest.json"

    _write_json(raw_path, {"wallets": raw_wallets})
    _write_rows(positions_path, cleaned_positions, WHALE_POSITION_COLUMNS)
    _write_rows(fills_path, cleaned_fills, WHALE_FILL_COLUMNS)

    manifest = HyperliquidWhaleSnapshotManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=config.dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=source_available_at,
        wallet_count=len(config.wallets),
        position_count=len(cleaned_positions),
        fill_count=len(cleaned_fills),
        wallets=tuple(wallet.address.lower() for wallet in config.wallets),
        raw_path=raw_path,
        positions_path=positions_path,
        fills_path=fills_path,
        manifest_path=manifest_path,
        raw_sha256=_file_sha256(raw_path),
        positions_sha256=_file_sha256(positions_path),
        fills_sha256=_file_sha256(fills_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config)
    return manifest


def _fetch_user_state(
    address: str,
    config: HyperliquidWhaleSnapshotConfig,
    fetch_info: InfoFetcher,
) -> dict[str, object]:
    payload = fetch_info({"type": "clearinghouseState", "user": address}, config.base_url)
    if not isinstance(payload, dict):
        raise HyperliquidWhaleDatasetError("clearinghouseState response must be an object")
    return dict(payload)


def _fetch_user_fills(
    address: str,
    config: HyperliquidWhaleSnapshotConfig,
    fetch_info: InfoFetcher,
) -> list[dict[str, object]]:
    request: dict[str, object] = {
        "type": "userFills",
        "user": address,
        "aggregateByTime": config.aggregate_fills_by_time,
    }
    if config.fills_start_time is not None:
        request = {
            "type": "userFillsByTime",
            "user": address,
            "startTime": _timestamp_ms(config.fills_start_time),
            "aggregateByTime": config.aggregate_fills_by_time,
        }
        if config.fills_end_time is not None:
            request["endTime"] = _timestamp_ms(config.fills_end_time)
    payload = fetch_info(request, config.base_url)
    if not isinstance(payload, list):
        raise HyperliquidWhaleDatasetError("user fills response must be a list")
    return [dict(item) for item in payload]


def _fetch_hyperliquid_info(request_payload: dict[str, object], base_url: str) -> object:
    request = urllib.request.Request(
        base_url,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "crypto-trade-research/ct133",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _normalize_position_rows(
    state: dict[str, object],
    *,
    wallet_address: str,
    source_available_at: str,
    venue: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in list(state.get("assetPositions", ())):
        position = dict(dict(item).get("position", {}))
        leverage = dict(position.get("leverage", {}) or {})
        size = _parse_decimal(position.get("szi"), "szi")
        symbol = _required_text(position, "coin")
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "venue": venue.lower(),
                "wallet_address": wallet_address,
                "source_available_at": source_available_at,
                "symbol": symbol.upper(),
                "side": "long" if size > 0 else "short",
                "position_size": size,
                "notional_usd": abs(_parse_decimal(position.get("positionValue"), "positionValue")),
                "entry_price": _parse_optional_decimal(position.get("entryPx"), "entryPx"),
                "mark_price": _parse_optional_decimal(position.get("markPx"), "markPx"),
                "unrealized_pnl_usd": _parse_optional_decimal(
                    position.get("unrealizedPnl"), "unrealizedPnl"
                ),
                "return_on_equity": _parse_optional_decimal(
                    position.get("returnOnEquity"), "returnOnEquity"
                ),
                "leverage_type": str(leverage.get("type", "")),
                "leverage_value": _parse_optional_decimal(leverage.get("value"), "leverage.value"),
                "liquidation_price": _parse_optional_decimal(
                    position.get("liquidationPx"), "liquidationPx"
                ),
            }
        )
    return rows


def _normalize_fill_rows(
    fills: list[dict[str, object]],
    *,
    wallet_address: str,
    source_available_at: str,
    venue: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for fill in fills:
        price = _parse_decimal(fill.get("px"), "px")
        size = _parse_decimal(fill.get("sz"), "sz")
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "venue": venue.lower(),
                "wallet_address": wallet_address,
                "source_available_at": source_available_at,
                "fill_time": _format_timestamp(_parse_ms_timestamp(fill.get("time"), "time")),
                "symbol": _required_text(fill, "coin").upper(),
                "side": _side_from_hyperliquid(fill.get("side")),
                "direction": _required_text(fill, "dir"),
                "price": price,
                "size": size,
                "notional_usd": abs(price * size),
                "closed_pnl_usd": _parse_optional_decimal(fill.get("closedPnl"), "closedPnl"),
                "fee": _parse_optional_decimal(fill.get("fee"), "fee"),
                "fee_token": str(fill.get("feeToken", "")),
                "order_id": _parse_optional_int(fill.get("oid"), "oid"),
                "trade_id": _parse_optional_int(fill.get("tid"), "tid"),
                "hash": str(fill.get("hash", "")),
                "crossed": bool(fill.get("crossed", False)),
            }
        )
    return rows


def _validate_config(config: HyperliquidWhaleSnapshotConfig) -> None:
    if not config.wallets:
        raise HyperliquidWhaleDatasetError("wallets must not be empty")
    for wallet in config.wallets:
        _validate_address(wallet.address)
    for value, name in (
        (config.generated_at, "generated_at"),
        (config.fills_start_time, "fills_start_time"),
        (config.fills_end_time, "fills_end_time"),
    ):
        if value is not None and value.tzinfo is None:
            raise HyperliquidWhaleDatasetError(f"{name} must be timezone-aware")
    if (
        config.fills_start_time is not None
        and config.fills_end_time is not None
        and config.fills_end_time < config.fills_start_time
    ):
        raise HyperliquidWhaleDatasetError("fills_end_time must be at or after fills_start_time")


def _validate_address(address: str) -> None:
    if len(address) != 42 or not address.startswith("0x"):
        raise HyperliquidWhaleDatasetError(f"invalid EVM wallet address: {address}")
    try:
        int(address[2:], 16)
    except ValueError as exc:
        raise HyperliquidWhaleDatasetError(f"invalid EVM wallet address: {address}") from exc


def _validate_and_sort_positions(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    for row in rows:
        if _as_decimal(row["notional_usd"]) < 0:
            raise HyperliquidWhaleDatasetError("position notional_usd must be non-negative")
    return sorted(rows, key=lambda row: (row["wallet_address"], row["symbol"]))


def _validate_and_sort_fills(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[object, ...]] = set()
    for row in rows:
        key = (row["wallet_address"], row["trade_id"], row["hash"])
        if key in seen:
            raise HyperliquidWhaleDatasetError(f"duplicate fill row: {key}")
        seen.add(key)
        if _as_decimal(row["notional_usd"]) < 0:
            raise HyperliquidWhaleDatasetError("fill notional_usd must be non-negative")
    return sorted(rows, key=lambda row: (row["wallet_address"], row["fill_time"], row["trade_id"]))


def _write_rows(path: Path, rows: Sequence[dict[str, object]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema([(column, _column_type(column)) for column in columns])
    normalized = [{column: row.get(column) for column in columns} for row in rows]
    table = pa.Table.from_pylist(normalized, schema=schema)
    pq.write_table(table, path)


def _column_type(column: str) -> pa.DataType:
    if column in {"source_available_at", "fill_time"}:
        return pa.string()
    if column in {"order_id", "trade_id", "leverage_value"}:
        return pa.float64()
    if column == "crossed":
        return pa.bool_()
    if column in {
        "position_size",
        "notional_usd",
        "entry_price",
        "mark_price",
        "unrealized_pnl_usd",
        "return_on_equity",
        "liquidation_price",
        "price",
        "size",
        "closed_pnl_usd",
        "fee",
    }:
        return pa.float64()
    return pa.string()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def _write_manifest(
    manifest: HyperliquidWhaleSnapshotManifest,
    config: HyperliquidWhaleSnapshotConfig,
) -> None:
    payload = asdict(manifest)
    payload["raw_path"] = str(manifest.raw_path)
    payload["positions_path"] = str(manifest.positions_path)
    payload["fills_path"] = str(manifest.fills_path)
    payload["manifest_path"] = str(manifest.manifest_path)
    payload["source"] = {
        "format": "hyperliquid_info_rest",
        "base_url": config.base_url,
        "include_fills": config.include_fills,
        "aggregate_fills_by_time": config.aggregate_fills_by_time,
    }
    _write_json(manifest.manifest_path, payload)


def _required_text(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if value is None or str(value) == "":
        raise HyperliquidWhaleDatasetError(f"missing required field: {field}")
    return str(value)


def _parse_decimal(value: object, field: str) -> float:
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HyperliquidWhaleDatasetError(f"invalid decimal field: {field}") from exc


def _parse_optional_decimal(value: object, field: str) -> float | None:
    if value is None or value == "":
        return None
    return _parse_decimal(value, field)


def _parse_optional_int(value: object, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HyperliquidWhaleDatasetError(f"invalid integer field: {field}") from exc


def _parse_ms_timestamp(value: object, field: str) -> datetime:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise HyperliquidWhaleDatasetError(f"invalid millisecond timestamp: {field}") from exc


def _side_from_hyperliquid(value: object) -> str:
    if value == "B":
        return "buy"
    if value == "A":
        return "sell"
    return str(value).lower()


def _as_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _timestamp_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_wallets(value: str) -> tuple[WatchedWallet, ...]:
    wallets: list[WatchedWallet] = []
    for item in value.split(","):
        raw = item.strip()
        if not raw:
            continue
        if "=" in raw:
            alias, address = raw.split("=", 1)
            wallets.append(WatchedWallet(address=address.strip(), alias=alias.strip()))
        else:
            wallets.append(WatchedWallet(address=raw))
    return tuple(wallets)


def _parse_timestamp_optional(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wallets", required=True, help="Comma-separated addresses or alias=address"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--generator-version", required=True)
    parser.add_argument("--fills-start-time")
    parser.add_argument("--fills-end-time")
    parser.add_argument("--skip-fills", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = generate_hyperliquid_whale_snapshot(
        HyperliquidWhaleSnapshotConfig(
            wallets=_parse_wallets(args.wallets),
            output_dir=args.output_dir,
            dataset_name=args.dataset_name,
            generator_version=args.generator_version,
            fills_start_time=_parse_timestamp_optional(args.fills_start_time),
            fills_end_time=_parse_timestamp_optional(args.fills_end_time),
            include_fills=not args.skip_fills,
        )
    )
    print(manifest.manifest_path)


if __name__ == "__main__":
    main()
