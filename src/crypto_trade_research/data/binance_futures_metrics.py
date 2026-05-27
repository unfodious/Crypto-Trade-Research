"""Binance Data Vision USD-M futures metrics ingestion for research features."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "research.binance_futures_metrics.v1"
GENERATOR_NAME = "crypto_trade_research.binance_futures_metrics_ingestion"
DATA_VISION_BASE_URL = "https://data.binance.vision"

FUTURES_METRICS_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "venue",
    "market_type",
    "symbol",
    "metrics_time",
    "source_available_at",
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
    "data_source",
    "source_file",
    "source_url",
    "source_sha256",
)
OPTIONAL_RATIO_FIELDS: tuple[str, ...] = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)

ZipFetcher = Callable[[str], bytes]


class BinanceFuturesMetricsDatasetError(ValueError):
    """Raised when futures metrics ingestion or validation fails."""


@dataclass(frozen=True, slots=True)
class BinanceFuturesMetricsDatasetConfig:
    symbols: tuple[str, ...]
    start_date: date
    end_date: date
    output_dir: Path
    dataset_name: str
    generator_version: str
    generated_at: datetime | None = None
    venue: str = "binance"
    market_type: str = "um_futures"
    base_url: str = DATA_VISION_BASE_URL
    max_workers: int = 8
    allow_missing_files: bool = False


@dataclass(frozen=True, slots=True)
class BinanceFuturesMetricsDatasetManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    row_count: int
    symbols: tuple[str, ...]
    min_metrics_time: str
    max_metrics_time: str
    source_file_count: int
    missing_file_count: int
    raw_path: Path
    cleaned_path: Path
    manifest_path: Path
    raw_sha256: str
    cleaned_sha256: str
    warnings: tuple[str, ...]


def generate_binance_futures_metrics_dataset(
    config: BinanceFuturesMetricsDatasetConfig,
    *,
    fetch_zip: ZipFetcher | None = None,
) -> BinanceFuturesMetricsDatasetManifest:
    """Download, validate, and write Binance Data Vision USD-M futures metrics."""

    _validate_config(config)
    zip_fetcher = fetch_zip or _fetch_url_bytes
    raw_rows, missing_files = _download_metrics_rows(config, zip_fetcher)
    if not raw_rows:
        raise BinanceFuturesMetricsDatasetError("metrics source returned no rows")

    cleaned_rows, warnings = _validate_and_sort_metrics_rows(raw_rows)
    warnings.extend(_null_ratio_warnings(cleaned_rows))
    if missing_files:
        warnings.extend(f"missing metrics file: {url}" for url in missing_files)

    dataset_dir = config.output_dir / config.dataset_name
    raw_path = dataset_dir / "raw" / "futures_metrics.parquet"
    cleaned_path = dataset_dir / "clean" / "futures_metrics.parquet"
    manifest_path = dataset_dir / "manifest.json"
    _write_metrics_rows(raw_path, raw_rows)
    _write_metrics_rows(cleaned_path, cleaned_rows)

    generated_at = config.generated_at or datetime.now(UTC)
    min_metrics_time = min(_as_datetime(row["metrics_time"]) for row in cleaned_rows)
    max_metrics_time = max(_as_datetime(row["metrics_time"]) for row in cleaned_rows)
    manifest = BinanceFuturesMetricsDatasetManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=config.dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(generated_at),
        row_count=len(cleaned_rows),
        symbols=tuple(sorted({str(row["symbol"]) for row in cleaned_rows})),
        min_metrics_time=_format_timestamp(min_metrics_time),
        max_metrics_time=_format_timestamp(max_metrics_time),
        source_file_count=len(_source_urls(config)) - len(missing_files),
        missing_file_count=len(missing_files),
        raw_path=raw_path,
        cleaned_path=cleaned_path,
        manifest_path=manifest_path,
        raw_sha256=_file_sha256(raw_path),
        cleaned_sha256=_file_sha256(cleaned_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config)
    return manifest


def _download_metrics_rows(
    config: BinanceFuturesMetricsDatasetConfig,
    fetch_zip: ZipFetcher,
) -> tuple[list[dict[str, object]], list[str]]:
    raw_rows: list[dict[str, object]] = []
    missing_files: list[str] = []
    jobs = _source_urls(config)
    worker_count = min(config.max_workers, len(jobs))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_download_one_file, source, config, fetch_zip): source
            for source in jobs
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                raw_rows.extend(future.result())
            except FileNotFoundError:
                if not config.allow_missing_files:
                    raise
                missing_files.append(source.url)
    return raw_rows, missing_files


@dataclass(frozen=True, slots=True)
class _MetricsSource:
    symbol: str
    day: date
    url: str
    file_name: str


def _source_urls(config: BinanceFuturesMetricsDatasetConfig) -> list[_MetricsSource]:
    sources: list[_MetricsSource] = []
    current = config.start_date
    while current < config.end_date:
        for symbol in config.symbols:
            symbol_upper = symbol.upper()
            file_name = f"{symbol_upper}-metrics-{current.isoformat()}.zip"
            url = f"{config.base_url}/data/futures/um/daily/metrics/{symbol_upper}/{file_name}"
            sources.append(
                _MetricsSource(
                    symbol=symbol_upper,
                    day=current,
                    url=url,
                    file_name=file_name,
                )
            )
        current += timedelta(days=1)
    return sources


def _download_one_file(
    source: _MetricsSource,
    config: BinanceFuturesMetricsDatasetConfig,
    fetch_zip: ZipFetcher,
) -> list[dict[str, object]]:
    zip_bytes = fetch_zip(source.url)
    source_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csv_names) != 1:
            raise BinanceFuturesMetricsDatasetError(
                f"metrics zip must contain exactly one CSV: {source.url}"
            )
        with archive.open(csv_names[0]) as handle:
            text_handle = io.TextIOWrapper(handle, encoding="utf-8")
            reader = csv.DictReader(text_handle)
            if reader.fieldnames is None:
                raise BinanceFuturesMetricsDatasetError("metrics CSV must have a header")
            for row_number, row in enumerate(reader, start=2):
                try:
                    rows.append(
                        _normalize_metrics_row(
                            row,
                            config,
                            source_file=source.file_name,
                            source_url=source.url,
                            source_sha256=source_sha256,
                        )
                    )
                except BinanceFuturesMetricsDatasetError as error:
                    raise BinanceFuturesMetricsDatasetError(
                        f"{source.file_name}:{row_number}: {error}"
                    ) from error
    return rows


def _fetch_url_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "crypto-trade-research/ct178"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return bytes(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise FileNotFoundError(url) from error
        raise


def _normalize_metrics_row(
    row: dict[str, object],
    config: BinanceFuturesMetricsDatasetConfig,
    *,
    source_file: str,
    source_url: str,
    source_sha256: str,
) -> dict[str, object]:
    metrics_time = _parse_metrics_timestamp(_required_text(row, "create_time"), "create_time")
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": config.venue.lower(),
        "market_type": config.market_type.lower(),
        "symbol": _required_text(row, "symbol").upper(),
        "metrics_time": metrics_time,
        "source_available_at": metrics_time,
        "sum_open_interest": _parse_decimal(row.get("sum_open_interest"), "sum_open_interest"),
        "sum_open_interest_value": _parse_decimal(
            row.get("sum_open_interest_value"), "sum_open_interest_value"
        ),
        "count_toptrader_long_short_ratio": _parse_optional_decimal(
            row.get("count_toptrader_long_short_ratio"),
            "count_toptrader_long_short_ratio",
        ),
        "sum_toptrader_long_short_ratio": _parse_optional_decimal(
            row.get("sum_toptrader_long_short_ratio"),
            "sum_toptrader_long_short_ratio",
        ),
        "count_long_short_ratio": _parse_optional_decimal(
            row.get("count_long_short_ratio"),
            "count_long_short_ratio",
        ),
        "sum_taker_long_short_vol_ratio": _parse_optional_decimal(
            row.get("sum_taker_long_short_vol_ratio"),
            "sum_taker_long_short_vol_ratio",
        ),
        "data_source": "binance_data_vision_usdm_daily_metrics",
        "source_file": source_file,
        "source_url": source_url,
        "source_sha256": source_sha256,
    }


def _validate_config(config: BinanceFuturesMetricsDatasetConfig) -> None:
    if not config.symbols:
        raise BinanceFuturesMetricsDatasetError("symbols must not be empty")
    if config.end_date <= config.start_date:
        raise BinanceFuturesMetricsDatasetError("end_date must be after start_date")
    if config.max_workers <= 0:
        raise BinanceFuturesMetricsDatasetError("max_workers must be positive")


def _validate_and_sort_metrics_rows(
    rows: Sequence[dict[str, object]],
) -> tuple[list[dict[str, object]], list[str]]:
    warnings: list[str] = []
    seen_keys: set[tuple[object, ...]] = set()
    for row in rows:
        _validate_metrics_row(row)
        key = _metrics_identity_key(row)
        if key in seen_keys:
            raise BinanceFuturesMetricsDatasetError(f"duplicate metrics row: {_key_to_text(key)}")
        seen_keys.add(key)

    sorted_rows = sorted(rows, key=_metrics_sort_key)
    for symbol_rows in _group_rows(sorted_rows):
        for previous, current in zip(symbol_rows, symbol_rows[1:], strict=False):
            gap = _as_datetime(current["metrics_time"]) - _as_datetime(previous["metrics_time"])
            if gap > timedelta(minutes=10):
                gap_time = _format_timestamp(_as_datetime(current["metrics_time"]))
                warnings.append(
                    f"metrics interval gap exceeds 10m for {current['symbol']} at {gap_time}"
                )
    return list(sorted_rows), warnings


def _validate_metrics_row(row: dict[str, object]) -> None:
    if row["schema_version"] != SCHEMA_VERSION:
        raise BinanceFuturesMetricsDatasetError(
            f"unsupported schema_version: {row['schema_version']}"
        )
    if not str(row["symbol"]).endswith("USDT"):
        raise BinanceFuturesMetricsDatasetError("metrics symbol must be a USDT-settled symbol")
    if _as_datetime(row["source_available_at"]) < _as_datetime(row["metrics_time"]):
        raise BinanceFuturesMetricsDatasetError(
            "source_available_at must be at or after metrics_time"
        )
    required_non_negative_fields = (
        "sum_open_interest",
        "sum_open_interest_value",
    )
    for field in required_non_negative_fields:
        if _as_decimal(row[field]) < 0:
            raise BinanceFuturesMetricsDatasetError(f"{field} must be non-negative")
    for field in OPTIONAL_RATIO_FIELDS:
        value = row[field]
        if value is not None and _as_decimal(value) < 0:
            raise BinanceFuturesMetricsDatasetError(f"{field} must be non-negative")


def _null_ratio_warnings(rows: Sequence[dict[str, object]]) -> list[str]:
    warnings: list[str] = []
    for field in OPTIONAL_RATIO_FIELDS:
        null_count = sum(1 for row in rows if row[field] is None)
        if null_count:
            warnings.append(f"{field} has {null_count} null source values")
    return warnings


def _write_metrics_rows(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable_rows = [
        {column: _to_arrow_value(row[column]) for column in FUTURES_METRICS_COLUMNS} for row in rows
    ]
    pq.write_table(pa.Table.from_pylist(serializable_rows), path)


def _write_manifest(
    manifest: BinanceFuturesMetricsDatasetManifest,
    config: BinanceFuturesMetricsDatasetConfig,
) -> None:
    payload = asdict(manifest)
    payload["raw_path"] = str(manifest.raw_path)
    payload["cleaned_path"] = str(manifest.cleaned_path)
    payload["manifest_path"] = str(manifest.manifest_path)
    payload["source"] = {
        "format": "binance_data_vision_usdm_daily_metrics_zip",
        "base_url": config.base_url,
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "end_date_exclusive": True,
        "allow_missing_files": config.allow_missing_files,
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
        raise BinanceFuturesMetricsDatasetError(f"{field_name} must not be empty")
    return value


def _parse_decimal(value: object, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise BinanceFuturesMetricsDatasetError(f"{field_name} must be numeric") from error


def _parse_optional_decimal(value: object, field_name: str) -> Decimal | None:
    text_value = str(value or "").strip()
    if text_value.lower() in {"", "nan", "none", "null"}:
        return None
    return _parse_decimal(text_value, field_name)


def _parse_metrics_timestamp(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError as error:
        raise BinanceFuturesMetricsDatasetError(
            f"{field_name} must use YYYY-MM-DD HH:MM:SS"
        ) from error


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise BinanceFuturesMetricsDatasetError(f"{field_name} must be an ISO date") from error


def _parse_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BinanceFuturesMetricsDatasetError(
            f"{field_name} must be an RFC3339 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise BinanceFuturesMetricsDatasetError(f"{field_name} must be timezone-aware")
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


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _metrics_identity_key(row: dict[str, object]) -> tuple[object, ...]:
    return (row["venue"], row["market_type"], row["symbol"], row["metrics_time"])


def _metrics_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (row["venue"], row["market_type"], row["symbol"], row["metrics_time"])


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
    parser.add_argument("--start-date", required=True, help="Inclusive ISO start date.")
    parser.add_argument("--end-date", required=True, help="Exclusive ISO end date.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--generator-version", required=True)
    parser.add_argument("--generated-at", help="Optional RFC3339 timestamp for deterministic runs.")
    parser.add_argument("--base-url", default=DATA_VISION_BASE_URL)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--allow-missing-files", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_cli_args()
    generated_at = (
        _parse_timestamp(args.generated_at, "generated_at") if args.generated_at else None
    )
    manifest = generate_binance_futures_metrics_dataset(
        BinanceFuturesMetricsDatasetConfig(
            symbols=tuple(
                symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()
            ),
            start_date=_parse_date(args.start_date, "start_date"),
            end_date=_parse_date(args.end_date, "end_date"),
            output_dir=args.output_dir,
            dataset_name=args.dataset_name,
            generator_version=args.generator_version,
            generated_at=generated_at,
            base_url=args.base_url,
            max_workers=args.max_workers,
            allow_missing_files=args.allow_missing_files,
        )
    )
    print(manifest.manifest_path)


if __name__ == "__main__":
    main()
