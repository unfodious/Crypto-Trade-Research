"""Binance USD-M futures order-book depth forward snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "research.binance_futures_order_book_snapshot.v1"
GENERATOR_NAME = "crypto_trade_research.binance_futures_order_book"
ORDER_BOOK_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"
SUPPORTED_DEPTH_LIMITS = frozenset({5, 10, 20, 50, 100, 500, 1000})

DepthFetcher = Callable[[str, int, str], dict[str, object]]


class BinanceOrderBookSnapshotError(ValueError):
    """Raised when Binance order-book snapshot collection fails validation."""


@dataclass(frozen=True, slots=True)
class BinanceOrderBookSnapshotConfig:
    symbols: tuple[str, ...]
    output_dir: Path
    dataset_prefix: str
    generator_version: str
    generated_at: datetime | None = None
    limit: int = 20
    request_sleep_seconds: float = 0.05
    depth_url: str = ORDER_BOOK_DEPTH_URL

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BinanceOrderBookSnapshotConfig:
        return cls(
            symbols=tuple(str(symbol).upper() for symbol in payload["symbols"]),
            output_dir=Path(str(payload["output_dir"])),
            dataset_prefix=str(payload["dataset_prefix"]),
            generator_version=str(payload["generator_version"]),
            generated_at=_parse_timestamp_optional(payload.get("generated_at")),
            limit=int(payload.get("limit", 20)),
            request_sleep_seconds=float(payload.get("request_sleep_seconds", 0.05)),
            depth_url=str(payload.get("depth_url", ORDER_BOOK_DEPTH_URL)),
        )

    @classmethod
    def from_path(cls, path: Path) -> BinanceOrderBookSnapshotConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class BinanceOrderBookSnapshotManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    row_count: int
    summary_row_count: int
    level_row_count: int
    symbols: tuple[str, ...]
    depth_limit: int
    summary_path: Path
    levels_path: Path
    manifest_path: Path
    summary_sha256: str
    levels_sha256: str
    warnings: tuple[str, ...]


def generate_binance_order_book_snapshot(
    config: BinanceOrderBookSnapshotConfig,
    *,
    fetch_depth: DepthFetcher | None = None,
) -> BinanceOrderBookSnapshotManifest:
    """Fetch, normalize, and persist a point-in-time Binance futures depth snapshot."""

    _validate_config(config)
    generated_at = config.generated_at or datetime.now(UTC)
    dataset_name = f"{config.dataset_prefix}_{_compact_timestamp(generated_at)}"
    dataset_dir = config.output_dir / dataset_name
    depth_fetcher = fetch_depth or _fetch_depth
    summary_rows: list[dict[str, object]] = []
    level_rows: list[dict[str, object]] = []
    warnings: list[str] = []

    for symbol in config.symbols:
        try:
            payload = depth_fetcher(symbol, config.limit, config.depth_url)
            summary_row, symbol_level_rows = _normalize_depth_payload(
                symbol=symbol,
                payload=payload,
                source_available_at=generated_at,
                depth_limit=config.limit,
            )
            summary_rows.append(summary_row)
            level_rows.extend(symbol_level_rows)
        except Exception as exc:  # noqa: BLE001 - snapshot should preserve partial failures.
            warnings.append(f"{symbol} order-book depth failed: {exc}")

        if config.request_sleep_seconds > 0:
            time.sleep(config.request_sleep_seconds)

    if not summary_rows and not level_rows:
        raise BinanceOrderBookSnapshotError("all Binance order-book sources returned no rows")

    summary_path = dataset_dir / "clean" / "order_book_summary.parquet"
    levels_path = dataset_dir / "clean" / "order_book_levels.parquet"
    manifest_path = dataset_dir / "manifest.json"
    _write_rows(summary_path, summary_rows)
    _write_rows(levels_path, level_rows)

    manifest = BinanceOrderBookSnapshotManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(generated_at),
        row_count=len(summary_rows) + len(level_rows),
        summary_row_count=len(summary_rows),
        level_row_count=len(level_rows),
        symbols=tuple(sorted(row["symbol"] for row in summary_rows)),
        depth_limit=config.limit,
        summary_path=summary_path,
        levels_path=levels_path,
        manifest_path=manifest_path,
        summary_sha256=_file_sha256(summary_path),
        levels_sha256=_file_sha256(levels_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config)
    _write_run_summary(config, manifest)
    return manifest


def _fetch_depth(symbol: str, limit: int, base_url: str) -> dict[str, object]:
    query = urllib.parse.urlencode({"symbol": symbol, "limit": limit})
    request = urllib.request.Request(
        f"{base_url}?{query}",
        headers={"User-Agent": "crypto-trade-research/ct158"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise BinanceOrderBookSnapshotError("order-book depth response must be an object")
    return dict(payload)


def _normalize_depth_payload(
    *,
    symbol: str,
    payload: dict[str, object],
    source_available_at: datetime,
    depth_limit: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    bids = _parse_levels(payload.get("bids"), "bids")
    asks = _parse_levels(payload.get("asks"), "asks")
    if not bids:
        raise BinanceOrderBookSnapshotError("bids must not be empty")
    if not asks:
        raise BinanceOrderBookSnapshotError("asks must not be empty")

    best_bid_price = bids[0][0]
    best_ask_price = asks[0][0]
    if best_bid_price <= 0 or best_ask_price <= 0:
        raise BinanceOrderBookSnapshotError("best bid/ask must be positive")
    if best_bid_price >= best_ask_price:
        raise BinanceOrderBookSnapshotError("best bid must be below best ask")

    mid_price = (best_bid_price + best_ask_price) / Decimal("2")
    last_update_id = _required_int(payload, "lastUpdateId")
    event_time = _parse_ms_timestamp_optional(payload.get("E"))
    transaction_time = _parse_ms_timestamp_optional(payload.get("T"))
    bid_quantity_total = sum(quantity for _, quantity in bids)
    ask_quantity_total = sum(quantity for _, quantity in asks)
    bid_notional_total = sum(price * quantity for price, quantity in bids)
    ask_notional_total = sum(price * quantity for price, quantity in asks)
    largest_bid_price, largest_bid_quantity = max(bids, key=lambda level: level[0] * level[1])
    largest_ask_price, largest_ask_quantity = max(asks, key=lambda level: level[0] * level[1])
    largest_bid_notional = largest_bid_price * largest_bid_quantity
    largest_ask_notional = largest_ask_price * largest_ask_quantity

    summary_row = {
        "schema_version": SCHEMA_VERSION,
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": symbol.upper(),
        "depth_limit": depth_limit,
        "event_time": event_time,
        "transaction_time": transaction_time,
        "source_available_at": source_available_at,
        "last_update_id": last_update_id,
        "best_bid_price": best_bid_price,
        "best_ask_price": best_ask_price,
        "mid_price": mid_price,
        "spread_bps": _bps((best_ask_price - best_bid_price) / mid_price),
        "bid_quantity_total": bid_quantity_total,
        "ask_quantity_total": ask_quantity_total,
        "bid_notional_total": bid_notional_total,
        "ask_notional_total": ask_notional_total,
        "quantity_imbalance": _imbalance(bid_quantity_total, ask_quantity_total),
        "notional_imbalance": _imbalance(bid_notional_total, ask_notional_total),
        "largest_bid_notional": largest_bid_notional,
        "largest_bid_distance_bps": _bid_distance_bps(largest_bid_price, mid_price),
        "largest_ask_notional": largest_ask_notional,
        "largest_ask_distance_bps": _ask_distance_bps(largest_ask_price, mid_price),
        "levels_per_side": min(len(bids), len(asks)),
        "data_source": "binance_fapi_depth",
    }

    level_rows = _normalize_side_levels(
        symbol=symbol,
        side="bid",
        levels=bids,
        mid_price=mid_price,
        event_time=event_time,
        transaction_time=transaction_time,
        source_available_at=source_available_at,
        last_update_id=last_update_id,
    ) + _normalize_side_levels(
        symbol=symbol,
        side="ask",
        levels=asks,
        mid_price=mid_price,
        event_time=event_time,
        transaction_time=transaction_time,
        source_available_at=source_available_at,
        last_update_id=last_update_id,
    )
    return summary_row, level_rows


def _normalize_side_levels(
    *,
    symbol: str,
    side: str,
    levels: list[tuple[Decimal, Decimal]],
    mid_price: Decimal,
    event_time: datetime | None,
    transaction_time: datetime | None,
    source_available_at: datetime,
    last_update_id: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, (price, quantity) in enumerate(levels, start=1):
        distance_bps = _bid_distance_bps(price, mid_price)
        if side == "ask":
            distance_bps = _ask_distance_bps(price, mid_price)
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "venue": "binance",
                "market_type": "um_futures",
                "symbol": symbol.upper(),
                "side": side,
                "level": index,
                "price": price,
                "quantity": quantity,
                "notional": price * quantity,
                "mid_price": mid_price,
                "distance_bps": distance_bps,
                "event_time": event_time,
                "transaction_time": transaction_time,
                "source_available_at": source_available_at,
                "last_update_id": last_update_id,
                "data_source": "binance_fapi_depth",
            }
        )
    return rows


def _parse_levels(value: object, field: str) -> list[tuple[Decimal, Decimal]]:
    if not isinstance(value, list):
        raise BinanceOrderBookSnapshotError(f"{field} must be a list")
    levels: list[tuple[Decimal, Decimal]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, list | tuple) or len(item) < 2:
            raise BinanceOrderBookSnapshotError(f"{field}[{index}] must include price and quantity")
        price = _parse_positive_decimal(item[0], f"{field}[{index}].price")
        quantity = _parse_non_negative_decimal(item[1], f"{field}[{index}].quantity")
        levels.append((price, quantity))
    return levels


def _validate_config(config: BinanceOrderBookSnapshotConfig) -> None:
    if not config.symbols:
        raise BinanceOrderBookSnapshotError("symbols must not be empty")
    if config.limit not in SUPPORTED_DEPTH_LIMITS:
        raise BinanceOrderBookSnapshotError("unsupported Binance order-book depth limit")
    if config.request_sleep_seconds < 0:
        raise BinanceOrderBookSnapshotError("request_sleep_seconds must be non-negative")
    if config.generated_at is not None and config.generated_at.tzinfo is None:
        raise BinanceOrderBookSnapshotError("generated_at must be timezone-aware")


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist([_serializable_row(row) for row in rows]), path)


def _serializable_row(row: dict[str, object]) -> dict[str, object]:
    return {key: _to_arrow_value(value) for key, value in row.items()}


def _write_manifest(
    manifest: BinanceOrderBookSnapshotManifest,
    config: BinanceOrderBookSnapshotConfig,
) -> None:
    payload = asdict(manifest)
    payload["summary_path"] = str(manifest.summary_path)
    payload["levels_path"] = str(manifest.levels_path)
    payload["manifest_path"] = str(manifest.manifest_path)
    payload["source"] = {
        "depth_url": config.depth_url,
        "limit": config.limit,
        "format": "binance_usdm_futures_public_rest",
        "history_limit_note": (
            "Order-book depth is a current visible-liquidity snapshot, not historical backfill. "
            "Use forward collection and persistence/imbalance validation before treating large "
            "visible levels as signal."
        ),
    }
    manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_run_summary(
    config: BinanceOrderBookSnapshotConfig,
    manifest: BinanceOrderBookSnapshotManifest,
) -> None:
    run_dir = config.output_dir / config.dataset_prefix
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "research.binance_futures_order_book_run.v1",
        "generator_name": GENERATOR_NAME,
        "generator_version": config.generator_version,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "latest_manifest_path": str(manifest.manifest_path),
        "latest_dataset_name": manifest.dataset_name,
        "latest_generated_at": manifest.generated_at,
        "row_count": manifest.row_count,
        "summary_row_count": manifest.summary_row_count,
        "level_row_count": manifest.level_row_count,
        "symbols": list(manifest.symbols),
        "depth_limit": manifest.depth_limit,
        "warnings": list(manifest.warnings),
        "notes": "Research-only public REST snapshot. No orders are submitted or modified.",
    }
    (run_dir / "order_book_run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_int(row: dict[str, object], field: str) -> int:
    value = row.get(field)
    if value is None or str(value) == "":
        raise BinanceOrderBookSnapshotError(f"missing required field: {field}")
    return int(str(value))


def _parse_positive_decimal(value: object, field: str) -> Decimal:
    parsed = _parse_decimal(value, field)
    if parsed <= 0:
        raise BinanceOrderBookSnapshotError(f"{field} must be positive")
    return parsed


def _parse_non_negative_decimal(value: object, field: str) -> Decimal:
    parsed = _parse_decimal(value, field)
    if parsed < 0:
        raise BinanceOrderBookSnapshotError(f"{field} must be non-negative")
    return parsed


def _parse_decimal(value: object, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise BinanceOrderBookSnapshotError(f"invalid decimal for {field}: {value!r}") from exc


def _parse_ms_timestamp_optional(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    return datetime.fromtimestamp(int(str(value)) / 1000, tz=UTC)


def _to_arrow_value(value: object) -> object:
    if isinstance(value, datetime):
        return value
    if isinstance(value, Decimal):
        return float(value)
    return value


def _imbalance(left: Decimal, right: Decimal) -> Decimal:
    denominator = left + right
    if denominator == 0:
        return Decimal("0")
    return (left - right) / denominator


def _bid_distance_bps(price: Decimal, mid_price: Decimal) -> Decimal:
    return _bps((mid_price - price) / mid_price)


def _ask_distance_bps(price: Decimal, mid_price: Decimal) -> Decimal:
    return _bps((price - mid_price) / mid_price)


def _bps(value: Decimal) -> Decimal:
    return value * Decimal("10000")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compact_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp_optional(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise BinanceOrderBookSnapshotError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = generate_binance_order_book_snapshot(
        BinanceOrderBookSnapshotConfig.from_path(args.config)
    )
    print(manifest.manifest_path)


if __name__ == "__main__":
    main()
