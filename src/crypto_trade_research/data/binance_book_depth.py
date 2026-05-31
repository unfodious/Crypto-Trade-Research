"""Binance Data Vision USD-M book-depth archive ingestion for research features."""

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

SCHEMA_VERSION = "research.binance_book_depth.v1"
FEATURE_SCHEMA_VERSION = "research.binance_book_depth_features.v1"
GENERATOR_NAME = "crypto_trade_research.binance_book_depth_ingestion"
DATA_VISION_BASE_URL = "https://data.binance.vision"
EXPECTED_PERCENTAGES = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)

BOOK_DEPTH_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "venue",
    "market_type",
    "symbol",
    "depth_time",
    "source_available_at",
    "percentage",
    "side",
    "distance_pct",
    "depth",
    "notional",
    "data_source",
    "source_file",
    "source_url",
    "source_sha256",
)

BOOK_DEPTH_FEATURE_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "venue",
    "market_type",
    "symbol",
    "depth_time",
    "source_available_at",
    "bd_bid_notional_1pct",
    "bd_bid_notional_2pct",
    "bd_bid_notional_5pct",
    "bd_ask_notional_1pct",
    "bd_ask_notional_2pct",
    "bd_ask_notional_5pct",
    "bd_imbalance_1pct",
    "bd_imbalance_2pct",
    "bd_imbalance_5pct",
    "bd_total_notional_1pct",
    "bd_total_notional_2pct",
    "bd_total_notional_5pct",
    "bd_band_count",
    "data_source",
)

ZipFetcher = Callable[[str], bytes]
HeadFetcher = Callable[[str], tuple[int, int | None]]


class BinanceBookDepthError(ValueError):
    """Raised when book-depth archive validation or ingestion fails."""


@dataclass(frozen=True, slots=True)
class BinanceBookDepthDatasetConfig:
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
class BinanceBookDepthDatasetManifest:
    schema_version: str
    feature_schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    row_count: int
    feature_row_count: int
    symbols: tuple[str, ...]
    min_depth_time: str
    max_depth_time: str
    source_file_count: int
    missing_file_count: int
    raw_path: Path
    cleaned_path: Path
    features_path: Path
    manifest_path: Path
    raw_sha256: str
    cleaned_sha256: str
    features_sha256: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BinanceBookDepthCoverageConfig:
    symbols: tuple[str, ...]
    windows: tuple[tuple[str, date, date], ...]
    output_json_path: Path
    output_markdown_path: Path | None = None
    base_url: str = DATA_VISION_BASE_URL
    max_workers: int = 16


@dataclass(frozen=True, slots=True)
class BinanceBookDepthFeatureCacheConfig:
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
class BinanceBookDepthFeatureCacheManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    source_row_count: int
    feature_row_count: int
    symbols: tuple[str, ...]
    min_depth_time: str
    max_depth_time: str
    source_file_count: int
    missing_file_count: int
    features_path: Path
    manifest_path: Path
    features_sha256: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BookDepthSource:
    symbol: str
    day: date
    url: str
    file_name: str


def generate_binance_book_depth_dataset(
    config: BinanceBookDepthDatasetConfig,
    *,
    fetch_zip: ZipFetcher | None = None,
) -> BinanceBookDepthDatasetManifest:
    """Download, validate, and write Binance Data Vision USD-M book-depth rows."""

    _validate_dataset_config(config)
    raw_rows, missing_files = _download_book_depth_rows(config, fetch_zip or _fetch_url_bytes)
    if not raw_rows:
        raise BinanceBookDepthError("book-depth source returned no rows")

    cleaned_rows, warnings = _validate_and_sort_book_depth_rows(raw_rows)
    if missing_files:
        warnings.extend(f"missing book-depth file: {url}" for url in missing_files)
    feature_rows = _feature_rows_from_depth_rows(cleaned_rows, config)

    dataset_dir = config.output_dir / config.dataset_name
    raw_path = dataset_dir / "raw" / "book_depth.parquet"
    cleaned_path = dataset_dir / "clean" / "book_depth.parquet"
    features_path = dataset_dir / "features" / "book_depth_features.parquet"
    manifest_path = dataset_dir / "manifest.json"
    _write_rows(raw_path, raw_rows, BOOK_DEPTH_COLUMNS)
    _write_rows(cleaned_path, cleaned_rows, BOOK_DEPTH_COLUMNS)
    _write_rows(features_path, feature_rows, BOOK_DEPTH_FEATURE_COLUMNS)

    generated_at = config.generated_at or datetime.now(UTC)
    min_depth_time = min(_as_datetime(row["depth_time"]) for row in cleaned_rows)
    max_depth_time = max(_as_datetime(row["depth_time"]) for row in cleaned_rows)
    manifest = BinanceBookDepthDatasetManifest(
        schema_version=SCHEMA_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        dataset_name=config.dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(generated_at),
        row_count=len(cleaned_rows),
        feature_row_count=len(feature_rows),
        symbols=tuple(sorted({str(row["symbol"]) for row in cleaned_rows})),
        min_depth_time=_format_timestamp(min_depth_time),
        max_depth_time=_format_timestamp(max_depth_time),
        source_file_count=len(_source_urls(config)) - len(missing_files),
        missing_file_count=len(missing_files),
        raw_path=raw_path,
        cleaned_path=cleaned_path,
        features_path=features_path,
        manifest_path=manifest_path,
        raw_sha256=_file_sha256(raw_path),
        cleaned_sha256=_file_sha256(cleaned_path),
        features_sha256=_file_sha256(features_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config)
    return manifest


def write_binance_book_depth_coverage_report(
    config: BinanceBookDepthCoverageConfig,
    *,
    fetch_head: HeadFetcher | None = None,
) -> dict[str, object]:
    """Write a HEAD-based availability and size estimate for Data Vision bookDepth files."""

    _validate_coverage_config(config)
    head_fetcher = fetch_head or _fetch_url_head
    sources = [
        _source
        for _, start_date, end_date in config.windows
        for _source in _source_urls_for(config.symbols, start_date, end_date, config.base_url)
    ]
    window_by_day = {
        current: window_name
        for window_name, start_date, end_date in config.windows
        for current in _date_range(start_date, end_date)
    }
    rows = _check_coverage_sources(sources, window_by_day, head_fetcher, config.max_workers)
    report = _coverage_report_payload(config, rows)
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if config.output_markdown_path is not None:
        config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        config.output_markdown_path.write_text(_coverage_markdown(report), encoding="utf-8")
    return report


def generate_binance_book_depth_feature_cache(
    config: BinanceBookDepthFeatureCacheConfig,
    *,
    fetch_zip: ZipFetcher | None = None,
) -> BinanceBookDepthFeatureCacheManifest:
    """Stream Data Vision book-depth files into an aggregated feature parquet cache."""

    _validate_feature_cache_config(config)
    dataset_dir = config.output_dir / config.dataset_name
    features_path = dataset_dir / "features" / "book_depth_features.parquet"
    manifest_path = dataset_dir / "manifest.json"
    features_path.parent.mkdir(parents=True, exist_ok=True)

    jobs = _source_urls_for(config.symbols, config.start_date, config.end_date, config.base_url)
    fetcher = fetch_zip or _fetch_url_bytes
    writer: pq.ParquetWriter | None = None
    source_row_count = 0
    feature_row_count = 0
    source_file_count = 0
    missing_files: list[str] = []
    warnings: list[str] = []
    symbols: set[str] = set()
    min_depth_time: datetime | None = None
    max_depth_time: datetime | None = None

    worker_count = min(config.max_workers, len(jobs))
    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(_download_one_file, source, config, fetcher): source
                for source in jobs
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    raw_rows = future.result()
                except FileNotFoundError:
                    if not config.allow_missing_files:
                        raise
                    missing_files.append(source.url)
                    continue
                cleaned_rows, file_warnings = _validate_and_sort_book_depth_rows(raw_rows)
                feature_rows = _feature_rows_from_depth_rows(cleaned_rows, config)
                if not feature_rows:
                    continue
                table = _rows_to_table(feature_rows, BOOK_DEPTH_FEATURE_COLUMNS)
                if writer is None:
                    writer = pq.ParquetWriter(features_path, table.schema)
                writer.write_table(table)
                source_file_count += 1
                source_row_count += len(cleaned_rows)
                feature_row_count += len(feature_rows)
                warnings.extend(file_warnings)
                symbols.update(str(row["symbol"]) for row in feature_rows)
                file_min = min(_as_datetime(row["depth_time"]) for row in feature_rows)
                file_max = max(_as_datetime(row["depth_time"]) for row in feature_rows)
                min_depth_time = (
                    file_min if min_depth_time is None else min(min_depth_time, file_min)
                )
                max_depth_time = (
                    file_max if max_depth_time is None else max(max_depth_time, file_max)
                )
    finally:
        if writer is not None:
            writer.close()

    if feature_row_count == 0 or min_depth_time is None or max_depth_time is None:
        raise BinanceBookDepthError("book-depth feature cache source returned no rows")
    if missing_files:
        warnings.extend(f"missing book-depth file: {url}" for url in missing_files)

    manifest = BinanceBookDepthFeatureCacheManifest(
        schema_version=FEATURE_SCHEMA_VERSION,
        dataset_name=config.dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(config.generated_at or datetime.now(UTC)),
        source_row_count=source_row_count,
        feature_row_count=feature_row_count,
        symbols=tuple(sorted(symbols)),
        min_depth_time=_format_timestamp(min_depth_time),
        max_depth_time=_format_timestamp(max_depth_time),
        source_file_count=source_file_count,
        missing_file_count=len(missing_files),
        features_path=features_path,
        manifest_path=manifest_path,
        features_sha256=_file_sha256(features_path),
        warnings=tuple(warnings),
    )
    _write_feature_cache_manifest(manifest, config)
    return manifest


def _download_book_depth_rows(
    config: BinanceBookDepthDatasetConfig,
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


def _download_one_file(
    source: _BookDepthSource,
    config: BinanceBookDepthDatasetConfig,
    fetch_zip: ZipFetcher,
) -> list[dict[str, object]]:
    zip_bytes = fetch_zip(source.url)
    source_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csv_names) != 1:
            raise BinanceBookDepthError(
                f"book-depth zip must contain exactly one CSV: {source.url}"
            )
        with archive.open(csv_names[0]) as handle:
            text_handle = io.TextIOWrapper(handle, encoding="utf-8")
            reader = csv.DictReader(text_handle)
            if reader.fieldnames is None:
                raise BinanceBookDepthError("book-depth CSV must have a header")
            for row_number, row in enumerate(reader, start=2):
                try:
                    rows.append(
                        _normalize_book_depth_row(
                            row,
                            source,
                            config,
                            source_sha256=source_sha256,
                        )
                    )
                except BinanceBookDepthError as error:
                    raise BinanceBookDepthError(
                        f"{source.file_name}:{row_number}: {error}"
                    ) from error
    return rows


def _normalize_book_depth_row(
    row: dict[str, object],
    source: _BookDepthSource,
    config: BinanceBookDepthDatasetConfig,
    *,
    source_sha256: str,
) -> dict[str, object]:
    depth_time = _parse_source_timestamp(_required_text(row, "timestamp"), "timestamp")
    percentage = int(_parse_decimal(row.get("percentage"), "percentage"))
    if percentage == 0:
        raise BinanceBookDepthError("percentage must not be zero")
    depth = _parse_decimal(row.get("depth"), "depth")
    notional = _parse_decimal(row.get("notional"), "notional")
    return {
        "schema_version": SCHEMA_VERSION,
        "venue": config.venue.lower(),
        "market_type": config.market_type.lower(),
        "symbol": source.symbol,
        "depth_time": depth_time,
        "source_available_at": depth_time,
        "percentage": percentage,
        "side": "bid" if percentage < 0 else "ask",
        "distance_pct": abs(percentage),
        "depth": depth,
        "notional": notional,
        "data_source": "binance_data_vision_usdm_daily_book_depth",
        "source_file": source.file_name,
        "source_url": source.url,
        "source_sha256": source_sha256,
    }


def _validate_and_sort_book_depth_rows(
    rows: Sequence[dict[str, object]],
) -> tuple[list[dict[str, object]], list[str]]:
    warnings: list[str] = []
    seen_keys: set[tuple[object, ...]] = set()
    for row in rows:
        _validate_book_depth_row(row)
        key = _book_depth_identity_key(row)
        if key in seen_keys:
            raise BinanceBookDepthError(f"duplicate book-depth row: {_key_to_text(key)}")
        seen_keys.add(key)
    sorted_rows = sorted(rows, key=_book_depth_sort_key)
    for group_key, group_rows in _timestamp_groups(sorted_rows).items():
        percentages = tuple(sorted(int(row["percentage"]) for row in group_rows))
        if percentages != EXPECTED_PERCENTAGES:
            warnings.append(
                "unexpected book-depth percentage bands for "
                f"{_key_to_text(group_key)}: {percentages}"
            )
    return list(sorted_rows), warnings


def _validate_book_depth_row(row: dict[str, object]) -> None:
    if row["schema_version"] != SCHEMA_VERSION:
        raise BinanceBookDepthError(f"unsupported schema_version: {row['schema_version']}")
    if not str(row["symbol"]).endswith("USDT"):
        raise BinanceBookDepthError("book-depth symbol must be a USDT-settled symbol")
    if _as_datetime(row["source_available_at"]) < _as_datetime(row["depth_time"]):
        raise BinanceBookDepthError("source_available_at must be at or after depth_time")
    if int(row["percentage"]) not in EXPECTED_PERCENTAGES:
        raise BinanceBookDepthError(f"unsupported percentage band: {row['percentage']}")
    if _as_decimal(row["depth"]) < 0:
        raise BinanceBookDepthError("depth must be non-negative")
    if _as_decimal(row["notional"]) < 0:
        raise BinanceBookDepthError("notional must be non-negative")


def _feature_rows_from_depth_rows(
    rows: Sequence[dict[str, object]],
    config: BinanceBookDepthDatasetConfig,
) -> list[dict[str, object]]:
    feature_rows: list[dict[str, object]] = []
    for group_rows in _timestamp_groups(rows).values():
        first = group_rows[0]
        notional_by_band = {
            int(row["percentage"]): _as_decimal(row["notional"]) for row in group_rows
        }
        bid_1 = notional_by_band[-1]
        bid_2 = notional_by_band[-1] + notional_by_band[-2]
        bid_5 = sum((notional_by_band[band] for band in (-1, -2, -3, -4, -5)), Decimal("0"))
        ask_1 = notional_by_band[1]
        ask_2 = notional_by_band[1] + notional_by_band[2]
        ask_5 = sum((notional_by_band[band] for band in (1, 2, 3, 4, 5)), Decimal("0"))
        feature_rows.append(
            {
                "schema_version": FEATURE_SCHEMA_VERSION,
                "venue": config.venue.lower(),
                "market_type": config.market_type.lower(),
                "symbol": first["symbol"],
                "depth_time": first["depth_time"],
                "source_available_at": first["source_available_at"],
                "bd_bid_notional_1pct": bid_1,
                "bd_bid_notional_2pct": bid_2,
                "bd_bid_notional_5pct": bid_5,
                "bd_ask_notional_1pct": ask_1,
                "bd_ask_notional_2pct": ask_2,
                "bd_ask_notional_5pct": ask_5,
                "bd_imbalance_1pct": _imbalance(bid_1, ask_1),
                "bd_imbalance_2pct": _imbalance(bid_2, ask_2),
                "bd_imbalance_5pct": _imbalance(bid_5, ask_5),
                "bd_total_notional_1pct": bid_1 + ask_1,
                "bd_total_notional_2pct": bid_2 + ask_2,
                "bd_total_notional_5pct": bid_5 + ask_5,
                "bd_band_count": len(group_rows),
                "data_source": "binance_data_vision_usdm_daily_book_depth",
            }
        )
    return sorted(feature_rows, key=_book_depth_sort_key)


def _imbalance(bid_notional: Decimal, ask_notional: Decimal) -> float | None:
    total = bid_notional + ask_notional
    if total == 0:
        return None
    return float((bid_notional - ask_notional) / total)


def _source_urls(config: BinanceBookDepthDatasetConfig) -> list[_BookDepthSource]:
    return _source_urls_for(config.symbols, config.start_date, config.end_date, config.base_url)


def _source_urls_for(
    symbols: Sequence[str],
    start_date: date,
    end_date: date,
    base_url: str,
) -> list[_BookDepthSource]:
    sources: list[_BookDepthSource] = []
    for current in _date_range(start_date, end_date):
        for symbol in symbols:
            symbol_upper = symbol.upper()
            file_name = f"{symbol_upper}-bookDepth-{current.isoformat()}.zip"
            url = f"{base_url}/data/futures/um/daily/bookDepth/{symbol_upper}/{file_name}"
            sources.append(
                _BookDepthSource(
                    symbol=symbol_upper,
                    day=current,
                    url=url,
                    file_name=file_name,
                )
            )
    return sources


def _check_coverage_sources(
    sources: Sequence[_BookDepthSource],
    window_by_day: dict[date, str],
    fetch_head: HeadFetcher,
    max_workers: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    worker_count = min(max_workers, len(sources))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(fetch_head, source.url): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                status, content_length = future.result()
            except FileNotFoundError:
                status, content_length = 404, None
            rows.append(
                {
                    "window": window_by_day[source.day],
                    "symbol": source.symbol,
                    "date": source.day.isoformat(),
                    "url": source.url,
                    "available": status == 200,
                    "status": status,
                    "content_length": content_length,
                }
            )
    return sorted(rows, key=lambda item: (item["window"], item["symbol"], item["date"]))


def _coverage_report_payload(
    config: BinanceBookDepthCoverageConfig,
    rows: Sequence[dict[str, object]],
) -> dict[str, object]:
    by_window_symbol: list[dict[str, object]] = []
    totals_by_key: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (str(row["window"]), str(row["symbol"]))
        totals_by_key.setdefault(key, []).append(row)
    for (window, symbol), key_rows in sorted(totals_by_key.items()):
        available_rows = [row for row in key_rows if bool(row["available"])]
        size_bytes = sum(int(row["content_length"] or 0) for row in available_rows)
        by_window_symbol.append(
            {
                "window": window,
                "symbol": symbol,
                "expected_files": len(key_rows),
                "available_files": len(available_rows),
                "missing_files": len(key_rows) - len(available_rows),
                "coverage_pct": len(available_rows) / len(key_rows) if key_rows else 0.0,
                "estimated_compressed_bytes": size_bytes,
            }
        )
    total_expected = len(rows)
    total_available = sum(1 for row in rows if bool(row["available"]))
    return {
        "schema_version": "research.binance_book_depth_coverage.v1",
        "generated_at": _format_timestamp(datetime.now(UTC)),
        "base_url": config.base_url,
        "symbols": list(config.symbols),
        "windows": [
            {
                "name": name,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "end_date_exclusive": True,
            }
            for name, start, end in config.windows
        ],
        "summary": {
            "expected_files": total_expected,
            "available_files": total_available,
            "missing_files": total_expected - total_available,
            "coverage_pct": total_available / total_expected if total_expected else 0.0,
            "estimated_compressed_bytes": sum(
                int(row["content_length"] or 0) for row in rows if bool(row["available"])
            ),
        },
        "by_window_symbol": by_window_symbol,
        "missing_files": [
            {
                "window": row["window"],
                "symbol": row["symbol"],
                "date": row["date"],
                "url": row["url"],
                "status": row["status"],
            }
            for row in rows
            if not bool(row["available"])
        ],
    }


def _coverage_markdown(report: dict[str, object]) -> str:
    summary = dict(report["summary"])
    lines = [
        "# Binance BookDepth Coverage",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Expected files | `{summary['expected_files']}` |",
        f"| Available files | `{summary['available_files']}` |",
        f"| Missing files | `{summary['missing_files']}` |",
        f"| Coverage | `{float(summary['coverage_pct']):.2%}` |",
        "| Estimated compressed size | "
        f"`{_format_bytes(int(summary['estimated_compressed_bytes']))}` |",
        "",
        "| Window | Symbol | Available / Expected | Coverage | Estimated compressed size |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in report["by_window_symbol"]:
        lines.append(
            f"| `{row['window']}` | `{row['symbol']}` | "
            f"`{row['available_files']} / {row['expected_files']}` | "
            f"`{float(row['coverage_pct']):.2%}` | "
            f"`{_format_bytes(int(row['estimated_compressed_bytes']))}` |"
        )
    missing_files = list(report["missing_files"])
    lines.extend(["", "## Missing Files", ""])
    if not missing_files:
        lines.append("None.")
    else:
        for row in missing_files[:100]:
            lines.append(
                f"- `{row['window']}` `{row['symbol']}` `{row['date']}` status `{row['status']}`"
            )
        if len(missing_files) > 100:
            lines.append(f"- ... {len(missing_files) - 100} additional missing files omitted")
    return "\n".join(lines) + "\n"


def _fetch_url_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "crypto-trade-research/ct205"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return bytes(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise FileNotFoundError(url) from error
        raise


def _fetch_url_head(url: str) -> tuple[int, int | None]:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "crypto-trade-research/ct205"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            content_length = response.headers.get("content-length")
            return response.status, int(content_length) if content_length else None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise FileNotFoundError(url) from error
        return error.code, None


def _validate_dataset_config(config: BinanceBookDepthDatasetConfig) -> None:
    if not config.symbols:
        raise BinanceBookDepthError("symbols must not be empty")
    if config.end_date <= config.start_date:
        raise BinanceBookDepthError("end_date must be after start_date")
    if config.max_workers <= 0:
        raise BinanceBookDepthError("max_workers must be positive")


def _validate_feature_cache_config(config: BinanceBookDepthFeatureCacheConfig) -> None:
    if not config.symbols:
        raise BinanceBookDepthError("symbols must not be empty")
    if config.end_date <= config.start_date:
        raise BinanceBookDepthError("end_date must be after start_date")
    if config.max_workers <= 0:
        raise BinanceBookDepthError("max_workers must be positive")


def _validate_coverage_config(config: BinanceBookDepthCoverageConfig) -> None:
    if not config.symbols:
        raise BinanceBookDepthError("symbols must not be empty")
    if not config.windows:
        raise BinanceBookDepthError("windows must not be empty")
    if config.max_workers <= 0:
        raise BinanceBookDepthError("max_workers must be positive")
    for name, start_date, end_date in config.windows:
        if not name:
            raise BinanceBookDepthError("window name must not be empty")
        if end_date <= start_date:
            raise BinanceBookDepthError(f"window {name} end_date must be after start_date")


def _write_rows(path: Path, rows: Sequence[dict[str, object]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(_rows_to_table(rows, columns), path)


def _rows_to_table(rows: Sequence[dict[str, object]], columns: Sequence[str]) -> pa.Table:
    serializable_rows = [
        {column: _to_arrow_value(row[column]) for column in columns} for row in rows
    ]
    return pa.Table.from_pylist(serializable_rows)


def _write_manifest(
    manifest: BinanceBookDepthDatasetManifest,
    config: BinanceBookDepthDatasetConfig,
) -> None:
    payload = asdict(manifest)
    for field_name in ("raw_path", "cleaned_path", "features_path", "manifest_path"):
        payload[field_name] = str(payload[field_name])
    payload["source"] = {
        "format": "binance_data_vision_usdm_daily_book_depth_zip",
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


def _write_feature_cache_manifest(
    manifest: BinanceBookDepthFeatureCacheManifest,
    config: BinanceBookDepthFeatureCacheConfig,
) -> None:
    payload = asdict(manifest)
    for field_name in ("features_path", "manifest_path"):
        payload[field_name] = str(payload[field_name])
    payload["source"] = {
        "format": "binance_data_vision_usdm_daily_book_depth_zip",
        "base_url": config.base_url,
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "end_date_exclusive": True,
        "allow_missing_files": config.allow_missing_files,
        "features_only": True,
    }
    manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_text(row: dict[str, object], field_name: str) -> str:
    value = str(row.get(field_name, "")).strip()
    if not value:
        raise BinanceBookDepthError(f"{field_name} must not be empty")
    return value


def _parse_decimal(value: object, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise BinanceBookDepthError(f"{field_name} must be numeric") from error


def _parse_source_timestamp(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError as error:
        raise BinanceBookDepthError(f"{field_name} must use YYYY-MM-DD HH:MM:SS") from error


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise BinanceBookDepthError(f"{field_name} must be an ISO date") from error


def _parse_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BinanceBookDepthError(f"{field_name} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise BinanceBookDepthError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _date_range(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current < end_date:
        yield current
        current += timedelta(days=1)


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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _book_depth_identity_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["depth_time"],
        row["percentage"],
    )


def _book_depth_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["depth_time"],
        row.get("percentage", 0),
    )


def _timestamp_groups(
    rows: Sequence[dict[str, object]],
) -> dict[tuple[object, ...], list[dict[str, object]]]:
    groups: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in rows:
        key = (row["venue"], row["market_type"], row["symbol"], row["depth_time"])
        groups.setdefault(key, []).append(row)
    return groups


def _key_to_text(key: Iterable[object]) -> str:
    return "|".join(str(part) for part in key)


def _format_bytes(byte_count: int) -> str:
    if byte_count >= 1024 * 1024 * 1024:
        return f"{byte_count / (1024 * 1024 * 1024):.2f} GiB"
    if byte_count >= 1024 * 1024:
        return f"{byte_count / (1024 * 1024):.2f} MiB"
    if byte_count >= 1024:
        return f"{byte_count / 1024:.2f} KiB"
    return f"{byte_count} B"


def _parse_symbols(value: str) -> tuple[str, ...]:
    return tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())


def _parse_windows(value: str) -> tuple[tuple[str, date, date], ...]:
    windows: list[tuple[str, date, date]] = []
    for item in value.split(","):
        if not item.strip():
            continue
        parts = item.split(":")
        if len(parts) != 3:
            raise BinanceBookDepthError("windows must use name:start:end comma-separated format")
        windows.append(
            (
                parts[0],
                _parse_date(parts[1], "window start"),
                _parse_date(parts[2], "window end"),
            )
        )
    return tuple(windows)


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Download and ingest bookDepth zip files.")
    ingest.add_argument("--symbols", required=True, help="Comma-separated USD-M symbols.")
    ingest.add_argument("--start-date", required=True, help="Inclusive ISO start date.")
    ingest.add_argument("--end-date", required=True, help="Exclusive ISO end date.")
    ingest.add_argument("--output-dir", type=Path, required=True)
    ingest.add_argument("--dataset-name", required=True)
    ingest.add_argument("--generator-version", required=True)
    ingest.add_argument("--generated-at", help="Optional RFC3339 timestamp for deterministic runs.")
    ingest.add_argument("--base-url", default=DATA_VISION_BASE_URL)
    ingest.add_argument("--max-workers", type=int, default=8)
    ingest.add_argument("--allow-missing-files", action="store_true")

    feature_cache = subparsers.add_parser(
        "feature-cache",
        help="Stream bookDepth zip files into an aggregated feature parquet cache.",
    )
    feature_cache.add_argument("--symbols", required=True, help="Comma-separated USD-M symbols.")
    feature_cache.add_argument("--start-date", required=True, help="Inclusive ISO start date.")
    feature_cache.add_argument("--end-date", required=True, help="Exclusive ISO end date.")
    feature_cache.add_argument("--output-dir", type=Path, required=True)
    feature_cache.add_argument("--dataset-name", required=True)
    feature_cache.add_argument("--generator-version", required=True)
    feature_cache.add_argument(
        "--generated-at",
        help="Optional RFC3339 timestamp for deterministic runs.",
    )
    feature_cache.add_argument("--base-url", default=DATA_VISION_BASE_URL)
    feature_cache.add_argument("--max-workers", type=int, default=8)
    feature_cache.add_argument("--allow-missing-files", action="store_true")

    coverage = subparsers.add_parser("coverage", help="HEAD-check bookDepth archive coverage.")
    coverage.add_argument("--symbols", required=True, help="Comma-separated USD-M symbols.")
    coverage.add_argument(
        "--windows",
        required=True,
        help="Comma-separated name:start:end windows, end exclusive.",
    )
    coverage.add_argument("--output-json-path", type=Path, required=True)
    coverage.add_argument("--output-markdown-path", type=Path)
    coverage.add_argument("--base-url", default=DATA_VISION_BASE_URL)
    coverage.add_argument("--max-workers", type=int, default=16)
    return parser.parse_args()


def main() -> None:
    args = _parse_cli_args()
    if args.command == "coverage":
        report = write_binance_book_depth_coverage_report(
            BinanceBookDepthCoverageConfig(
                symbols=_parse_symbols(args.symbols),
                windows=_parse_windows(args.windows),
                output_json_path=args.output_json_path,
                output_markdown_path=args.output_markdown_path,
                base_url=args.base_url,
                max_workers=args.max_workers,
            )
        )
        print(args.output_json_path)
        print(json.dumps(report["summary"], sort_keys=True))
        return

    generated_at = (
        _parse_timestamp(args.generated_at, "generated_at") if args.generated_at else None
    )
    if args.command == "feature-cache":
        manifest = generate_binance_book_depth_feature_cache(
            BinanceBookDepthFeatureCacheConfig(
                symbols=_parse_symbols(args.symbols),
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
        return

    manifest = generate_binance_book_depth_dataset(
        BinanceBookDepthDatasetConfig(
            symbols=_parse_symbols(args.symbols),
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
