"""Binance USD-M funding-rate dataset ingestion for research features."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "research.funding_rate.v1"
GENERATOR_NAME = "crypto_trade_research.funding_rate_ingestion"
BINANCE_FUNDING_RATE_URL = "https://fapi.binance.com/fapi/v1/fundingRate"

FUNDING_RATE_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "venue",
    "market_type",
    "symbol",
    "funding_time",
    "source_available_at",
    "funding_rate",
    "mark_price",
    "data_source",
)

FundingPageFetcher = Callable[[str, datetime, datetime, int, str], list[dict[str, object]]]


class FundingRateDatasetError(ValueError):
    """Raised when funding-rate ingestion or validation fails."""


@dataclass(frozen=True, slots=True)
class FundingRateDatasetConfig:
    symbols: tuple[str, ...]
    start_time: datetime
    end_time: datetime
    output_dir: Path
    dataset_name: str
    generator_version: str
    generated_at: datetime | None = None
    venue: str = "binance"
    market_type: str = "um_futures"
    base_url: str = BINANCE_FUNDING_RATE_URL
    limit: int = 1000
    request_sleep_seconds: float = 0.05


@dataclass(frozen=True, slots=True)
class FundingRateDatasetManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    row_count: int
    symbols: tuple[str, ...]
    min_funding_time: str
    max_funding_time: str
    raw_path: Path
    cleaned_path: Path
    manifest_path: Path
    raw_sha256: str
    cleaned_sha256: str
    warnings: tuple[str, ...]


def generate_funding_rate_dataset(
    config: FundingRateDatasetConfig,
    *,
    fetch_page: FundingPageFetcher | None = None,
) -> FundingRateDatasetManifest:
    """Fetch, validate, and write a Binance USD-M funding-rate dataset."""

    _validate_config(config)
    page_fetcher = fetch_page or _fetch_binance_funding_page
    raw_rows: list[dict[str, object]] = []
    for symbol in config.symbols:
        raw_rows.extend(_fetch_symbol_rows(symbol.upper(), config, page_fetcher))

    if not raw_rows:
        raise FundingRateDatasetError("funding-rate source returned no rows")

    cleaned_rows, warnings = _validate_and_sort_funding_rows(raw_rows)
    dataset_dir = config.output_dir / config.dataset_name
    raw_path = dataset_dir / "raw" / "funding_rates.parquet"
    cleaned_path = dataset_dir / "clean" / "funding_rates.parquet"
    manifest_path = dataset_dir / "manifest.json"

    _write_funding_rows(raw_path, raw_rows)
    _write_funding_rows(cleaned_path, cleaned_rows)

    generated_at = config.generated_at or datetime.now(UTC)
    min_funding_time = min(_as_datetime(row["funding_time"]) for row in cleaned_rows)
    max_funding_time = max(_as_datetime(row["funding_time"]) for row in cleaned_rows)
    manifest = FundingRateDatasetManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=config.dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(generated_at),
        row_count=len(cleaned_rows),
        symbols=tuple(sorted({str(row["symbol"]) for row in cleaned_rows})),
        min_funding_time=_format_timestamp(min_funding_time),
        max_funding_time=_format_timestamp(max_funding_time),
        raw_path=raw_path,
        cleaned_path=cleaned_path,
        manifest_path=manifest_path,
        raw_sha256=_file_sha256(raw_path),
        cleaned_sha256=_file_sha256(cleaned_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config)
    return manifest


def _fetch_symbol_rows(
    symbol: str,
    config: FundingRateDatasetConfig,
    fetch_page: FundingPageFetcher,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    page_start = config.start_time
    while page_start <= config.end_time:
        page = fetch_page(symbol, page_start, config.end_time, config.limit, config.base_url)
        if not page:
            break
        normalized_page = [
            _normalize_funding_row(item, config.venue, config.market_type) for item in page
        ]
        rows.extend(normalized_page)
        last_time = max(_as_datetime(row["funding_time"]) for row in normalized_page)
        next_start = last_time + timedelta(milliseconds=1)
        if next_start <= page_start:
            raise FundingRateDatasetError(f"non-advancing funding pagination for {symbol}")
        page_start = next_start
        if len(page) < config.limit:
            break
        if config.request_sleep_seconds > 0:
            time.sleep(config.request_sleep_seconds)
    return rows


def _fetch_binance_funding_page(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    limit: int,
    base_url: str,
) -> list[dict[str, object]]:
    query = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "startTime": _timestamp_ms(start_time),
            "endTime": _timestamp_ms(end_time),
            "limit": limit,
        }
    )
    request = urllib.request.Request(
        f"{base_url}?{query}",
        headers={"User-Agent": "crypto-trade-research/ct128"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise FundingRateDatasetError("Binance funding-rate response must be a list")
    return [dict(item) for item in payload]


def _normalize_funding_row(
    row: dict[str, object],
    venue: str,
    market_type: str,
) -> dict[str, object]:
    funding_time = _parse_ms_timestamp(row.get("fundingTime"), "fundingTime")
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": venue.lower(),
        "market_type": market_type.lower(),
        "symbol": _required_text(row, "symbol").upper(),
        "funding_time": funding_time,
        "source_available_at": funding_time,
        "funding_rate": _parse_decimal(row.get("fundingRate"), "fundingRate"),
        "mark_price": _parse_optional_decimal(row.get("markPrice"), "markPrice"),
        "data_source": "binance_fapi_funding_rate",
    }


def _validate_config(config: FundingRateDatasetConfig) -> None:
    if not config.symbols:
        raise FundingRateDatasetError("symbols must not be empty")
    if config.start_time.tzinfo is None or config.end_time.tzinfo is None:
        raise FundingRateDatasetError("start_time and end_time must be timezone-aware")
    if config.end_time < config.start_time:
        raise FundingRateDatasetError("end_time must be at or after start_time")
    if config.limit <= 0 or config.limit > 1000:
        raise FundingRateDatasetError("limit must be between 1 and 1000")
    if config.request_sleep_seconds < 0:
        raise FundingRateDatasetError("request_sleep_seconds must be non-negative")


def _validate_and_sort_funding_rows(
    rows: Sequence[dict[str, object]],
) -> tuple[list[dict[str, object]], list[str]]:
    warnings: list[str] = []
    seen_keys: set[tuple[object, ...]] = set()
    for row in rows:
        _validate_funding_row(row)
        key = _funding_identity_key(row)
        if key in seen_keys:
            raise FundingRateDatasetError(f"duplicate funding row: {_key_to_text(key)}")
        seen_keys.add(key)

    sorted_rows = sorted(rows, key=_funding_sort_key)
    for symbol_rows in _group_rows(sorted_rows):
        for previous, current in zip(symbol_rows, symbol_rows[1:], strict=False):
            gap = _as_datetime(current["funding_time"]) - _as_datetime(previous["funding_time"])
            if gap > timedelta(hours=8, minutes=5):
                current_time = _format_timestamp(_as_datetime(current["funding_time"]))
                warnings.append(
                    f"funding interval gap exceeds 8h05m for {current['symbol']} at {current_time}"
                )
    return list(sorted_rows), warnings


def _validate_funding_row(row: dict[str, object]) -> None:
    if row["schema_version"] != SCHEMA_VERSION:
        raise FundingRateDatasetError(f"unsupported schema_version: {row['schema_version']}")
    if not str(row["symbol"]).endswith("USDT"):
        raise FundingRateDatasetError("funding symbol must be a USDT-settled symbol")
    funding_rate = _as_decimal(row["funding_rate"])
    if abs(funding_rate) > Decimal("0.05"):
        raise FundingRateDatasetError("funding_rate absolute value exceeds 5%")
    mark_price = row.get("mark_price")
    if mark_price is not None and _as_decimal(mark_price) <= 0:
        raise FundingRateDatasetError("mark_price must be positive when present")
    if _as_datetime(row["source_available_at"]) < _as_datetime(row["funding_time"]):
        raise FundingRateDatasetError("source_available_at must be at or after funding_time")


def _write_funding_rows(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable_rows = [
        {column: _to_arrow_value(row[column]) for column in FUNDING_RATE_COLUMNS} for row in rows
    ]
    pq.write_table(pa.Table.from_pylist(serializable_rows), path)


def _write_manifest(
    manifest: FundingRateDatasetManifest,
    config: FundingRateDatasetConfig,
) -> None:
    payload = asdict(manifest)
    payload["raw_path"] = str(manifest.raw_path)
    payload["cleaned_path"] = str(manifest.cleaned_path)
    payload["manifest_path"] = str(manifest.manifest_path)
    payload["source"] = {
        "format": "binance_usdm_funding_rate_rest",
        "endpoint": config.base_url,
        "start_time": _format_timestamp(config.start_time),
        "end_time": _format_timestamp(config.end_time),
        "limit": config.limit,
    }
    manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_text(row: dict[str, object], field_name: str) -> str:
    value = str(row.get(field_name, "")).strip()
    if not value:
        raise FundingRateDatasetError(f"{field_name} must not be empty")
    return value


def _parse_decimal(value: object, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise FundingRateDatasetError(f"{field_name} must be numeric") from error


def _parse_optional_decimal(value: object, field_name: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return _parse_decimal(value, field_name)


def _parse_ms_timestamp(value: object, field_name: str) -> datetime:
    try:
        timestamp_ms = int(str(value))
    except ValueError as error:
        raise FundingRateDatasetError(f"{field_name} must be a millisecond timestamp") from error
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


def _parse_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FundingRateDatasetError(f"{field_name} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise FundingRateDatasetError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)!r}")
    return value.astimezone(UTC)


def _as_decimal(value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"expected Decimal, got {type(value)!r}")
    return value


def _to_arrow_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _timestamp_ms(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _funding_identity_key(row: dict[str, object]) -> tuple[object, ...]:
    return (row["venue"], row["market_type"], row["symbol"], row["funding_time"])


def _funding_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (row["venue"], row["market_type"], row["symbol"], row["funding_time"])


def _key_to_text(key: Iterable[object]) -> str:
    return "|".join(str(part) for part in key)


def _group_rows(rows: Sequence[dict[str, object]]) -> list[list[dict[str, object]]]:
    groups: list[list[dict[str, object]]] = []
    for row in rows:
        key = (row["venue"], row["market_type"], row["symbol"])
        previous_key = None
        if groups:
            previous_key = (
                groups[-1][0]["venue"],
                groups[-1][0]["market_type"],
                groups[-1][0]["symbol"],
            )
        if previous_key != key:
            groups.append([])
        groups[-1].append(row)
    return groups


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", required=True, help="Comma-separated USD-M symbols.")
    parser.add_argument("--start-time", required=True, help="Inclusive RFC3339 start timestamp.")
    parser.add_argument("--end-time", required=True, help="Inclusive RFC3339 end timestamp.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--generator-version", required=True)
    parser.add_argument("--generated-at", help="Optional RFC3339 timestamp for deterministic runs.")
    parser.add_argument("--request-sleep-seconds", type=float, default=0.05)
    return parser.parse_args()


def main() -> None:
    args = _parse_cli_args()
    generated_at = (
        _parse_timestamp(args.generated_at, "generated_at") if args.generated_at else None
    )
    manifest = generate_funding_rate_dataset(
        FundingRateDatasetConfig(
            symbols=tuple(
                symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()
            ),
            start_time=_parse_timestamp(args.start_time, "start_time"),
            end_time=_parse_timestamp(args.end_time, "end_time"),
            output_dir=args.output_dir,
            dataset_name=args.dataset_name,
            generator_version=args.generator_version,
            generated_at=generated_at,
            request_sleep_seconds=args.request_sleep_seconds,
        )
    )
    print(manifest.manifest_path)


if __name__ == "__main__":
    main()
