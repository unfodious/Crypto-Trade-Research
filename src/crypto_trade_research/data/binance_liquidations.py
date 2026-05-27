"""Binance USD-M futures force-liquidation forward snapshots."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import websockets

SCHEMA_VERSION = "research.binance_futures_liquidation_snapshot.v1"
GENERATOR_NAME = "crypto_trade_research.binance_futures_liquidations"
DEFAULT_STREAM_URL = "wss://fstream.binance.com/market/ws/!forceOrder@arr"


class BinanceLiquidationSnapshotError(ValueError):
    """Raised when Binance liquidation snapshot collection fails validation."""


@dataclass(frozen=True, slots=True)
class BinanceLiquidationSnapshotConfig:
    symbols: tuple[str, ...]
    output_dir: Path
    dataset_prefix: str
    generator_version: str
    generated_at: datetime | None = None
    stream_url: str = DEFAULT_STREAM_URL
    capture_seconds: float = 70.0
    connect_timeout_seconds: float = 15.0
    message_timeout_seconds: float = 5.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BinanceLiquidationSnapshotConfig:
        return cls(
            symbols=tuple(str(symbol).upper() for symbol in payload["symbols"]),
            output_dir=Path(str(payload["output_dir"])),
            dataset_prefix=str(payload["dataset_prefix"]),
            generator_version=str(payload["generator_version"]),
            generated_at=_parse_timestamp_optional(payload.get("generated_at")),
            stream_url=str(payload.get("stream_url", DEFAULT_STREAM_URL)),
            capture_seconds=float(payload.get("capture_seconds", 70.0)),
            connect_timeout_seconds=float(payload.get("connect_timeout_seconds", 15.0)),
            message_timeout_seconds=float(payload.get("message_timeout_seconds", 5.0)),
        )

    @classmethod
    def from_path(cls, path: Path) -> BinanceLiquidationSnapshotConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class BinanceLiquidationSnapshotManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    capture_started_at: str
    capture_ended_at: str
    row_count: int
    event_count_total: int
    event_count_filtered_out: int
    symbols: tuple[str, ...]
    liquidations_path: Path
    manifest_path: Path
    liquidations_sha256: str
    warnings: tuple[str, ...]


async def generate_binance_liquidation_snapshot_async(
    config: BinanceLiquidationSnapshotConfig,
    *,
    messages: Iterable[str | bytes | dict[str, object]] | None = None,
) -> BinanceLiquidationSnapshotManifest:
    """Collect and persist a bounded Binance futures force-liquidation snapshot window."""

    _validate_config(config)
    generated_at = config.generated_at or datetime.now(UTC)
    dataset_name = f"{config.dataset_prefix}_{_compact_timestamp(generated_at)}"
    dataset_dir = config.output_dir / dataset_name
    capture_started_at = datetime.now(UTC)
    warnings: list[str] = []
    event_rows: list[dict[str, object]] = []
    event_count_total = 0
    event_count_filtered_out = 0
    symbols = frozenset(config.symbols)

    message_source = (
        _iter_static_messages(messages) if messages is not None else _stream_messages(config)
    )
    async for payload in message_source:
        try:
            normalized_payload = _decode_message(payload)
            events = _extract_events(normalized_payload)
            event_count_total += len(events)
            for event in events:
                order = _required_dict(event, "o")
                symbol = _required_text(order, "s").upper()
                if symbol not in symbols:
                    event_count_filtered_out += 1
                    continue
                event_rows.append(
                    _normalize_force_order_event(
                        event=event,
                        source_available_at=generated_at,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - preserve malformed event evidence as warning.
            warnings.append(f"liquidation message failed: {exc}")

    capture_ended_at = datetime.now(UTC)
    liquidations_path = dataset_dir / "clean" / "liquidations.parquet"
    manifest_path = dataset_dir / "manifest.json"
    _write_rows(liquidations_path, event_rows)
    manifest = BinanceLiquidationSnapshotManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(generated_at),
        capture_started_at=_format_timestamp(capture_started_at),
        capture_ended_at=_format_timestamp(capture_ended_at),
        row_count=len(event_rows),
        event_count_total=event_count_total,
        event_count_filtered_out=event_count_filtered_out,
        symbols=tuple(sorted(symbols)),
        liquidations_path=liquidations_path,
        manifest_path=manifest_path,
        liquidations_sha256=_file_sha256(liquidations_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config)
    _write_run_summary(config, manifest)
    return manifest


def generate_binance_liquidation_snapshot(
    config: BinanceLiquidationSnapshotConfig,
) -> BinanceLiquidationSnapshotManifest:
    return asyncio.run(generate_binance_liquidation_snapshot_async(config))


async def _stream_messages(config: BinanceLiquidationSnapshotConfig) -> AsyncIterator[str | bytes]:
    deadline = asyncio.get_running_loop().time() + config.capture_seconds
    try:
        async with asyncio.timeout(config.connect_timeout_seconds):
            connection = await websockets.connect(config.stream_url)
        async with connection:
            while asyncio.get_running_loop().time() < deadline:
                remaining_seconds = deadline - asyncio.get_running_loop().time()
                timeout = min(config.message_timeout_seconds, remaining_seconds)
                if timeout <= 0:
                    break
                try:
                    yield await asyncio.wait_for(connection.recv(), timeout=timeout)
                except TimeoutError:
                    continue
    except TimeoutError as exc:
        raise BinanceLiquidationSnapshotError("timed out connecting to Binance websocket") from exc


async def _iter_static_messages(
    messages: Iterable[str | bytes | dict[str, object]],
) -> AsyncIterator[str | bytes | dict[str, object]]:
    for message in messages:
        yield message


def _decode_message(payload: str | bytes | dict[str, object]) -> dict[str, object]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise BinanceLiquidationSnapshotError("websocket message must be an object")
    return parsed


def _extract_events(payload: dict[str, object]) -> list[dict[str, object]]:
    data = payload.get("data", payload)
    if isinstance(data, list):
        return [dict(item) for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    raise BinanceLiquidationSnapshotError("websocket data must be an object or list")


def _normalize_force_order_event(
    *,
    event: dict[str, object],
    source_available_at: datetime,
) -> dict[str, object]:
    order = _required_dict(event, "o")
    quantity = _parse_non_negative_decimal(order.get("q"), "q")
    price = _parse_non_negative_decimal(order.get("p"), "p")
    average_price = _parse_non_negative_decimal(order.get("ap"), "ap")
    last_filled_quantity = _parse_non_negative_decimal(order.get("l"), "l")
    filled_accumulated_quantity = _parse_non_negative_decimal(order.get("z"), "z")
    notional = average_price * filled_accumulated_quantity
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": "binance",
        "market_type": "um_futures",
        "event_type": _required_text(event, "e"),
        "event_time": _parse_ms_timestamp(event.get("E"), "E"),
        "source_available_at": source_available_at,
        "symbol": _required_text(order, "s").upper(),
        "side": _required_text(order, "S"),
        "order_type": _required_text(order, "o"),
        "time_in_force": _required_text(order, "f"),
        "original_quantity": quantity,
        "price": price,
        "average_price": average_price,
        "order_status": _required_text(order, "X"),
        "last_filled_quantity": last_filled_quantity,
        "filled_accumulated_quantity": filled_accumulated_quantity,
        "trade_time": _parse_ms_timestamp(order.get("T"), "T"),
        "notional": notional,
        "liquidation_direction": _liquidation_direction(_required_text(order, "S")),
        "data_source": "binance_usdm_force_order_stream",
    }


def _liquidation_direction(side: str) -> str:
    if side == "SELL":
        return "long_liquidation"
    if side == "BUY":
        return "short_liquidation"
    return "unknown"


def _validate_config(config: BinanceLiquidationSnapshotConfig) -> None:
    if not config.symbols:
        raise BinanceLiquidationSnapshotError("symbols must not be empty")
    if config.capture_seconds <= 0:
        raise BinanceLiquidationSnapshotError("capture_seconds must be positive")
    if config.connect_timeout_seconds <= 0:
        raise BinanceLiquidationSnapshotError("connect_timeout_seconds must be positive")
    if config.message_timeout_seconds <= 0:
        raise BinanceLiquidationSnapshotError("message_timeout_seconds must be positive")
    if config.generated_at is not None and config.generated_at.tzinfo is None:
        raise BinanceLiquidationSnapshotError("generated_at must be timezone-aware")


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        table = pa.Table.from_pylist([_serializable_row(row) for row in rows])
    else:
        table = pa.Table.from_pylist([], schema=_liquidation_schema())
    pq.write_table(table, path)


def _liquidation_schema() -> pa.Schema:
    return pa.schema(
        [
            ("schema_version", pa.string()),
            ("venue", pa.string()),
            ("market_type", pa.string()),
            ("event_type", pa.string()),
            ("event_time", pa.timestamp("us", tz="UTC")),
            ("source_available_at", pa.timestamp("us", tz="UTC")),
            ("symbol", pa.string()),
            ("side", pa.string()),
            ("order_type", pa.string()),
            ("time_in_force", pa.string()),
            ("original_quantity", pa.float64()),
            ("price", pa.float64()),
            ("average_price", pa.float64()),
            ("order_status", pa.string()),
            ("last_filled_quantity", pa.float64()),
            ("filled_accumulated_quantity", pa.float64()),
            ("trade_time", pa.timestamp("us", tz="UTC")),
            ("notional", pa.float64()),
            ("liquidation_direction", pa.string()),
            ("data_source", pa.string()),
        ]
    )


def _serializable_row(row: dict[str, object]) -> dict[str, object]:
    return {key: _to_arrow_value(value) for key, value in row.items()}


def _write_manifest(
    manifest: BinanceLiquidationSnapshotManifest,
    config: BinanceLiquidationSnapshotConfig,
) -> None:
    payload = asdict(manifest)
    payload["liquidations_path"] = str(manifest.liquidations_path)
    payload["manifest_path"] = str(manifest.manifest_path)
    payload["source"] = {
        "stream_url": config.stream_url,
        "format": "binance_usdm_futures_public_websocket",
        "history_limit_note": (
            "Force-order streams are forward-only snapshots. Binance publishes only the largest "
            "liquidation per symbol per 1000ms interval, and no event is pushed when no "
            "liquidation occurs in that interval."
        ),
    }
    manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_run_summary(
    config: BinanceLiquidationSnapshotConfig,
    manifest: BinanceLiquidationSnapshotManifest,
) -> None:
    run_dir = config.output_dir / config.dataset_prefix
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "research.binance_futures_liquidation_run.v1",
        "generator_name": GENERATOR_NAME,
        "generator_version": config.generator_version,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "latest_manifest_path": str(manifest.manifest_path),
        "latest_dataset_name": manifest.dataset_name,
        "latest_generated_at": manifest.generated_at,
        "capture_started_at": manifest.capture_started_at,
        "capture_ended_at": manifest.capture_ended_at,
        "row_count": manifest.row_count,
        "event_count_total": manifest.event_count_total,
        "event_count_filtered_out": manifest.event_count_filtered_out,
        "symbols": list(manifest.symbols),
        "warnings": list(manifest.warnings),
        "notes": (
            "Research-only public websocket snapshot. Empty windows are valid when no "
            "liquidation event is pushed. No orders are submitted or modified."
        ),
    }
    (run_dir / "liquidation_run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_dict(row: dict[str, object], field: str) -> dict[str, object]:
    value = row.get(field)
    if not isinstance(value, dict):
        raise BinanceLiquidationSnapshotError(f"missing required object: {field}")
    return value


def _required_text(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if value is None or str(value) == "":
        raise BinanceLiquidationSnapshotError(f"missing required field: {field}")
    return str(value)


def _parse_non_negative_decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise BinanceLiquidationSnapshotError(f"invalid decimal for {field}: {value!r}") from exc
    if parsed < 0:
        raise BinanceLiquidationSnapshotError(f"{field} must be non-negative")
    return parsed


def _parse_ms_timestamp(value: object, field: str) -> datetime:
    if value is None:
        raise BinanceLiquidationSnapshotError(f"missing timestamp: {field}")
    return datetime.fromtimestamp(int(str(value)) / 1000, tz=UTC)


def _to_arrow_value(value: object) -> object:
    if isinstance(value, datetime):
        return value
    if isinstance(value, Decimal):
        return float(value)
    return value


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
        raise BinanceLiquidationSnapshotError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = generate_binance_liquidation_snapshot(
        BinanceLiquidationSnapshotConfig.from_path(args.config)
    )
    print(manifest.manifest_path)


if __name__ == "__main__":
    main()
