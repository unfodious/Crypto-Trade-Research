"""Binance USD-M futures open-interest and crowding forward snapshots."""

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

SCHEMA_VERSION = "research.binance_futures_crowding_snapshot.v1"
GENERATOR_NAME = "crypto_trade_research.binance_futures_crowding"
OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"
OPEN_INTEREST_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"
GLOBAL_LONG_SHORT_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
TOP_LONG_SHORT_POSITION_URL = "https://fapi.binance.com/futures/data/topLongShortPositionRatio"
TOP_LONG_SHORT_ACCOUNT_URL = "https://fapi.binance.com/futures/data/topLongShortAccountRatio"

OpenInterestFetcher = Callable[[str, str], dict[str, object]]
SeriesFetcher = Callable[[str, str, int, str], list[dict[str, object]]]


class BinanceCrowdingSnapshotError(ValueError):
    """Raised when Binance crowding snapshot collection fails validation."""


@dataclass(frozen=True, slots=True)
class BinanceCrowdingSnapshotConfig:
    symbols: tuple[str, ...]
    output_dir: Path
    dataset_prefix: str
    generator_version: str
    generated_at: datetime | None = None
    period: str = "5m"
    limit: int = 1
    request_sleep_seconds: float = 0.05
    open_interest_url: str = OPEN_INTEREST_URL
    open_interest_hist_url: str = OPEN_INTEREST_HIST_URL
    global_long_short_url: str = GLOBAL_LONG_SHORT_URL
    top_long_short_position_url: str = TOP_LONG_SHORT_POSITION_URL
    top_long_short_account_url: str = TOP_LONG_SHORT_ACCOUNT_URL

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BinanceCrowdingSnapshotConfig:
        return cls(
            symbols=tuple(str(symbol).upper() for symbol in payload["symbols"]),
            output_dir=Path(str(payload["output_dir"])),
            dataset_prefix=str(payload["dataset_prefix"]),
            generator_version=str(payload["generator_version"]),
            generated_at=_parse_timestamp_optional(payload.get("generated_at")),
            period=str(payload.get("period", "5m")),
            limit=int(payload.get("limit", 1)),
            request_sleep_seconds=float(payload.get("request_sleep_seconds", 0.05)),
            open_interest_url=str(payload.get("open_interest_url", OPEN_INTEREST_URL)),
            open_interest_hist_url=str(
                payload.get("open_interest_hist_url", OPEN_INTEREST_HIST_URL)
            ),
            global_long_short_url=str(payload.get("global_long_short_url", GLOBAL_LONG_SHORT_URL)),
            top_long_short_position_url=str(
                payload.get("top_long_short_position_url", TOP_LONG_SHORT_POSITION_URL)
            ),
            top_long_short_account_url=str(
                payload.get("top_long_short_account_url", TOP_LONG_SHORT_ACCOUNT_URL)
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> BinanceCrowdingSnapshotConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class BinanceCrowdingSnapshotManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    row_count: int
    symbols: tuple[str, ...]
    period: str
    current_open_interest_path: Path
    open_interest_hist_path: Path
    global_long_short_path: Path
    top_long_short_position_path: Path
    top_long_short_account_path: Path
    manifest_path: Path
    current_open_interest_sha256: str
    open_interest_hist_sha256: str
    global_long_short_sha256: str
    top_long_short_position_sha256: str
    top_long_short_account_sha256: str
    warnings: tuple[str, ...]


def generate_binance_crowding_snapshot(
    config: BinanceCrowdingSnapshotConfig,
    *,
    fetch_open_interest: OpenInterestFetcher | None = None,
    fetch_open_interest_hist: SeriesFetcher | None = None,
    fetch_global_long_short: SeriesFetcher | None = None,
    fetch_top_long_short_position: SeriesFetcher | None = None,
    fetch_top_long_short_account: SeriesFetcher | None = None,
) -> BinanceCrowdingSnapshotManifest:
    """Fetch, normalize, and persist a point-in-time Binance futures crowding snapshot."""

    _validate_config(config)
    generated_at = config.generated_at or datetime.now(UTC)
    dataset_name = f"{config.dataset_prefix}_{_compact_timestamp(generated_at)}"
    dataset_dir = config.output_dir / dataset_name
    open_interest_rows: list[dict[str, object]] = []
    open_interest_hist_rows: list[dict[str, object]] = []
    global_long_short_rows: list[dict[str, object]] = []
    top_long_short_position_rows: list[dict[str, object]] = []
    top_long_short_account_rows: list[dict[str, object]] = []
    warnings: list[str] = []
    open_interest_fetcher = fetch_open_interest or _fetch_open_interest
    open_interest_hist_fetcher = fetch_open_interest_hist or _fetch_series
    global_long_short_fetcher = fetch_global_long_short or _fetch_series
    top_long_short_position_fetcher = fetch_top_long_short_position or _fetch_series
    top_long_short_account_fetcher = fetch_top_long_short_account or _fetch_series

    for symbol in config.symbols:
        try:
            open_interest_rows.append(
                _normalize_current_open_interest(
                    open_interest_fetcher(symbol, config.open_interest_url),
                    generated_at,
                )
            )
        except Exception as exc:  # noqa: BLE001 - snapshot should preserve partial failures.
            warnings.append(f"{symbol} current open interest failed: {exc}")

        try:
            open_interest_hist_rows.extend(
                _normalize_open_interest_hist_row(row, generated_at, config.period)
                for row in open_interest_hist_fetcher(
                    symbol,
                    config.period,
                    config.limit,
                    config.open_interest_hist_url,
                )
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{symbol} open interest history failed: {exc}")

        try:
            global_long_short_rows.extend(
                _normalize_global_long_short_row(row, generated_at, config.period)
                for row in global_long_short_fetcher(
                    symbol,
                    config.period,
                    config.limit,
                    config.global_long_short_url,
                )
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{symbol} global long/short failed: {exc}")

        try:
            top_long_short_position_rows.extend(
                _normalize_top_long_short_position_row(row, generated_at, config.period)
                for row in top_long_short_position_fetcher(
                    symbol,
                    config.period,
                    config.limit,
                    config.top_long_short_position_url,
                )
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{symbol} top trader position long/short failed: {exc}")

        try:
            top_long_short_account_rows.extend(
                _normalize_top_long_short_account_row(row, generated_at, config.period)
                for row in top_long_short_account_fetcher(
                    symbol,
                    config.period,
                    config.limit,
                    config.top_long_short_account_url,
                )
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{symbol} top trader account long/short failed: {exc}")

        if config.request_sleep_seconds > 0:
            time.sleep(config.request_sleep_seconds)

    if (
        not open_interest_rows
        and not open_interest_hist_rows
        and not global_long_short_rows
        and not top_long_short_position_rows
        and not top_long_short_account_rows
    ):
        raise BinanceCrowdingSnapshotError("all Binance crowding sources returned no rows")

    current_open_interest_path = dataset_dir / "clean" / "current_open_interest.parquet"
    open_interest_hist_path = dataset_dir / "clean" / "open_interest_hist.parquet"
    global_long_short_path = dataset_dir / "clean" / "global_long_short_ratio.parquet"
    top_long_short_position_path = dataset_dir / "clean" / "top_long_short_position_ratio.parquet"
    top_long_short_account_path = dataset_dir / "clean" / "top_long_short_account_ratio.parquet"
    manifest_path = dataset_dir / "manifest.json"
    _write_rows(current_open_interest_path, open_interest_rows)
    _write_rows(open_interest_hist_path, open_interest_hist_rows)
    _write_rows(global_long_short_path, global_long_short_rows)
    _write_rows(top_long_short_position_path, top_long_short_position_rows)
    _write_rows(top_long_short_account_path, top_long_short_account_rows)

    row_count = (
        len(open_interest_rows)
        + len(open_interest_hist_rows)
        + len(global_long_short_rows)
        + len(top_long_short_position_rows)
        + len(top_long_short_account_rows)
    )
    manifest = BinanceCrowdingSnapshotManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(generated_at),
        row_count=row_count,
        symbols=tuple(sorted(set(config.symbols))),
        period=config.period,
        current_open_interest_path=current_open_interest_path,
        open_interest_hist_path=open_interest_hist_path,
        global_long_short_path=global_long_short_path,
        top_long_short_position_path=top_long_short_position_path,
        top_long_short_account_path=top_long_short_account_path,
        manifest_path=manifest_path,
        current_open_interest_sha256=_file_sha256(current_open_interest_path),
        open_interest_hist_sha256=_file_sha256(open_interest_hist_path),
        global_long_short_sha256=_file_sha256(global_long_short_path),
        top_long_short_position_sha256=_file_sha256(top_long_short_position_path),
        top_long_short_account_sha256=_file_sha256(top_long_short_account_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config)
    _write_run_summary(config, manifest)
    return manifest


def _fetch_open_interest(symbol: str, base_url: str) -> dict[str, object]:
    query = urllib.parse.urlencode({"symbol": symbol})
    request = urllib.request.Request(
        f"{base_url}?{query}",
        headers={"User-Agent": "crypto-trade-research/ct151"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise BinanceCrowdingSnapshotError("open interest response must be an object")
    return dict(payload)


def _fetch_series(symbol: str, period: str, limit: int, base_url: str) -> list[dict[str, object]]:
    query = urllib.parse.urlencode({"symbol": symbol, "period": period, "limit": limit})
    request = urllib.request.Request(
        f"{base_url}?{query}",
        headers={"User-Agent": "crypto-trade-research/ct151"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise BinanceCrowdingSnapshotError("series response must be a list")
    return [dict(item) for item in payload]


def _normalize_current_open_interest(
    row: dict[str, object],
    source_available_at: datetime,
) -> dict[str, object]:
    event_time = _parse_ms_timestamp(row.get("time"), "time")
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": _required_text(row, "symbol").upper(),
        "event_time": event_time,
        "source_available_at": source_available_at,
        "open_interest": _parse_decimal(row.get("openInterest"), "openInterest"),
        "data_source": "binance_fapi_open_interest",
    }


def _normalize_open_interest_hist_row(
    row: dict[str, object],
    source_available_at: datetime,
    period: str,
) -> dict[str, object]:
    event_time = _parse_ms_timestamp(row.get("timestamp"), "timestamp")
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": _required_text(row, "symbol").upper(),
        "period": period,
        "event_time": event_time,
        "source_available_at": source_available_at,
        "sum_open_interest": _parse_decimal(row.get("sumOpenInterest"), "sumOpenInterest"),
        "sum_open_interest_value": _parse_decimal(
            row.get("sumOpenInterestValue"), "sumOpenInterestValue"
        ),
        "cmc_circulating_supply": _parse_optional_decimal(
            row.get("CMCCirculatingSupply"), "CMCCirculatingSupply"
        ),
        "data_source": "binance_futures_data_open_interest_hist",
    }


def _normalize_global_long_short_row(
    row: dict[str, object],
    source_available_at: datetime,
    period: str,
) -> dict[str, object]:
    event_time = _parse_ms_timestamp(row.get("timestamp"), "timestamp")
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": _required_text(row, "symbol").upper(),
        "period": period,
        "event_time": event_time,
        "source_available_at": source_available_at,
        "long_short_ratio": _parse_decimal(row.get("longShortRatio"), "longShortRatio"),
        "long_account": _parse_decimal(row.get("longAccount"), "longAccount"),
        "short_account": _parse_decimal(row.get("shortAccount"), "shortAccount"),
        "data_source": "binance_futures_data_global_long_short_account_ratio",
    }


def _normalize_top_long_short_position_row(
    row: dict[str, object],
    source_available_at: datetime,
    period: str,
) -> dict[str, object]:
    event_time = _parse_ms_timestamp(row.get("timestamp"), "timestamp")
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": _required_text(row, "symbol").upper(),
        "period": period,
        "event_time": event_time,
        "source_available_at": source_available_at,
        "long_short_ratio": _parse_decimal(row.get("longShortRatio"), "longShortRatio"),
        "long_position": _parse_decimal(row.get("longAccount"), "longAccount"),
        "short_position": _parse_decimal(row.get("shortAccount"), "shortAccount"),
        "data_source": "binance_futures_data_top_trader_long_short_position_ratio",
    }


def _normalize_top_long_short_account_row(
    row: dict[str, object],
    source_available_at: datetime,
    period: str,
) -> dict[str, object]:
    event_time = _parse_ms_timestamp(row.get("timestamp"), "timestamp")
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": "binance",
        "market_type": "um_futures",
        "symbol": _required_text(row, "symbol").upper(),
        "period": period,
        "event_time": event_time,
        "source_available_at": source_available_at,
        "long_short_ratio": _parse_decimal(row.get("longShortRatio"), "longShortRatio"),
        "long_account": _parse_decimal(row.get("longAccount"), "longAccount"),
        "short_account": _parse_decimal(row.get("shortAccount"), "shortAccount"),
        "data_source": "binance_futures_data_top_trader_long_short_account_ratio",
    }


def _validate_config(config: BinanceCrowdingSnapshotConfig) -> None:
    if not config.symbols:
        raise BinanceCrowdingSnapshotError("symbols must not be empty")
    if config.period not in {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}:
        raise BinanceCrowdingSnapshotError("unsupported Binance crowding period")
    if config.limit <= 0 or config.limit > 500:
        raise BinanceCrowdingSnapshotError("limit must be between 1 and 500")
    if config.request_sleep_seconds < 0:
        raise BinanceCrowdingSnapshotError("request_sleep_seconds must be non-negative")
    if config.generated_at is not None and config.generated_at.tzinfo is None:
        raise BinanceCrowdingSnapshotError("generated_at must be timezone-aware")


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist([_serializable_row(row) for row in rows]), path)


def _serializable_row(row: dict[str, object]) -> dict[str, object]:
    return {key: _to_arrow_value(value) for key, value in row.items()}


def _write_manifest(
    manifest: BinanceCrowdingSnapshotManifest,
    config: BinanceCrowdingSnapshotConfig,
) -> None:
    payload = asdict(manifest)
    payload["current_open_interest_path"] = str(manifest.current_open_interest_path)
    payload["open_interest_hist_path"] = str(manifest.open_interest_hist_path)
    payload["global_long_short_path"] = str(manifest.global_long_short_path)
    payload["top_long_short_position_path"] = str(manifest.top_long_short_position_path)
    payload["top_long_short_account_path"] = str(manifest.top_long_short_account_path)
    payload["manifest_path"] = str(manifest.manifest_path)
    payload["source"] = {
        "current_open_interest_url": config.open_interest_url,
        "open_interest_hist_url": config.open_interest_hist_url,
        "global_long_short_url": config.global_long_short_url,
        "top_long_short_position_url": config.top_long_short_position_url,
        "top_long_short_account_url": config.top_long_short_account_url,
        "period": config.period,
        "limit": config.limit,
        "format": "binance_usdm_futures_public_rest",
        "history_limit_note": (
            "openInterestHist, globalLongShortAccountRatio, topLongShortPositionRatio, "
            "and topLongShortAccountRatio expose only recent public history; this snapshot is "
            "forward-collected point-in-time evidence"
        ),
    }
    manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_run_summary(
    config: BinanceCrowdingSnapshotConfig,
    manifest: BinanceCrowdingSnapshotManifest,
) -> None:
    run_dir = config.output_dir / config.dataset_prefix
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "research.binance_futures_crowding_run.v1",
        "generator_name": GENERATOR_NAME,
        "generator_version": config.generator_version,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "latest_manifest_path": str(manifest.manifest_path),
        "latest_dataset_name": manifest.dataset_name,
        "latest_generated_at": manifest.generated_at,
        "row_count": manifest.row_count,
        "symbols": list(manifest.symbols),
        "period": manifest.period,
        "warnings": list(manifest.warnings),
        "notes": "Research-only public REST snapshot. No orders are submitted or modified.",
    }
    (run_dir / "crowding_run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_text(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if value is None or str(value) == "":
        raise BinanceCrowdingSnapshotError(f"missing required field: {field}")
    return str(value)


def _parse_decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise BinanceCrowdingSnapshotError(f"invalid decimal for {field}: {value!r}") from exc
    if parsed < 0:
        raise BinanceCrowdingSnapshotError(f"{field} must be non-negative")
    return parsed


def _parse_optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None or str(value) == "":
        return None
    return _parse_decimal(value, field)


def _parse_ms_timestamp(value: object, field: str) -> datetime:
    if value is None:
        raise BinanceCrowdingSnapshotError(f"missing timestamp: {field}")
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
        raise BinanceCrowdingSnapshotError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = generate_binance_crowding_snapshot(
        BinanceCrowdingSnapshotConfig.from_path(args.config)
    )
    print(manifest.manifest_path)


if __name__ == "__main__":
    main()
