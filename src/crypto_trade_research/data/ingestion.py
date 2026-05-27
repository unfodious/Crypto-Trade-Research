"""CSV-to-Parquet ingestion for research market-candle datasets."""

import argparse
import csv
import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "research.dataset.v1"
GENERATOR_NAME = "crypto_trade_research.market_dataset_ingestion"

MARKET_CANDLE_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "venue",
    "market_type",
    "symbol",
    "base_asset",
    "quote_asset",
    "timeframe",
    "open_time",
    "close_time",
    "source_available_at",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "data_source",
    "source_file",
    "checksum",
)
MAX_CANDLE_RANGE_TO_OPEN_RATIO = Decimal("1.0")

FUTURE_LABEL_COLUMNS = frozenset(
    {
        "forward_return_1",
        "forward_return_3",
        "forward_return_12",
        "max_favorable_excursion_r",
        "max_adverse_excursion_r",
        "target_before_stop",
        "expected_r_after_costs",
        "no_trade_reason",
        "gross_r",
        "net_r",
        "exit_time",
        "exit_reason",
    }
)


class DatasetValidationError(ValueError):
    """Raised when a source dataset violates the research data contract."""


@dataclass(frozen=True, slots=True)
class MarketDatasetConfig:
    source_csv: Path
    output_dir: Path
    dataset_name: str
    generator_version: str
    generated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    row_count: int
    min_close_time: str
    max_close_time: str
    raw_path: Path
    cleaned_path: Path
    manifest_path: Path
    source_sha256: str
    raw_sha256: str
    cleaned_sha256: str
    warnings: tuple[str, ...]


def generate_market_dataset(config: MarketDatasetConfig) -> DatasetManifest:
    """Generate raw and cleaned market-candle Parquet datasets from a CSV export."""

    source_rows = _read_csv_rows(config.source_csv)
    normalized_rows = [_normalize_market_candle(row) for row in source_rows]
    cleaned_rows, warnings = _validate_and_sort_market_candles(normalized_rows)

    dataset_dir = config.output_dir / config.dataset_name
    raw_path = dataset_dir / "raw" / "market_candles.parquet"
    cleaned_path = dataset_dir / "clean" / "market_candles.parquet"
    manifest_path = dataset_dir / "manifest.json"

    _write_market_candles(raw_path, normalized_rows)
    _write_market_candles(cleaned_path, cleaned_rows)

    generated_at = config.generated_at or datetime.now(UTC)
    min_close_time = min(_as_datetime(row["close_time"]) for row in cleaned_rows)
    max_close_time = max(_as_datetime(row["close_time"]) for row in cleaned_rows)

    manifest = DatasetManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=config.dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(generated_at),
        row_count=len(cleaned_rows),
        min_close_time=_format_timestamp(min_close_time),
        max_close_time=_format_timestamp(max_close_time),
        raw_path=raw_path,
        cleaned_path=cleaned_path,
        manifest_path=manifest_path,
        source_sha256=_file_sha256(config.source_csv),
        raw_sha256=_file_sha256(raw_path),
        cleaned_sha256=_file_sha256(cleaned_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config.source_csv)
    return manifest


def _read_csv_rows(source_csv: Path) -> list[dict[str, str]]:
    if not source_csv.exists():
        raise DatasetValidationError(f"source CSV does not exist: {source_csv}")

    with source_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DatasetValidationError("source CSV must have a header")

        field_names = set(reader.fieldnames)
        missing_columns = set(MARKET_CANDLE_COLUMNS) - field_names
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise DatasetValidationError(f"source CSV is missing required columns: {missing}")

        future_columns = field_names & FUTURE_LABEL_COLUMNS
        if future_columns:
            leaked = ", ".join(sorted(future_columns))
            raise DatasetValidationError(f"raw source includes future label fields: {leaked}")

        rows = list(reader)

    if not rows:
        raise DatasetValidationError("source CSV must contain at least one market candle")
    return rows


def _normalize_market_candle(row: dict[str, str]) -> dict[str, object]:
    normalized = {
        "schema_version": _required_text(row, "schema_version"),
        "venue": _required_text(row, "venue").lower(),
        "market_type": _required_text(row, "market_type").lower(),
        "symbol": _required_text(row, "symbol").upper(),
        "base_asset": _required_text(row, "base_asset").upper(),
        "quote_asset": _required_text(row, "quote_asset").upper(),
        "timeframe": _required_text(row, "timeframe").lower(),
        "open_time": _parse_timestamp(row["open_time"], "open_time"),
        "close_time": _parse_timestamp(row["close_time"], "close_time"),
        "source_available_at": _parse_timestamp(row["source_available_at"], "source_available_at"),
        "open": _parse_decimal(row["open"], "open"),
        "high": _parse_decimal(row["high"], "high"),
        "low": _parse_decimal(row["low"], "low"),
        "close": _parse_decimal(row["close"], "close"),
        "volume": _parse_decimal(row["volume"], "volume"),
        "quote_volume": _parse_decimal(row["quote_volume"], "quote_volume"),
        "number_of_trades": _parse_int(row["number_of_trades"], "number_of_trades"),
        "taker_buy_base_volume": _parse_decimal(
            row["taker_buy_base_volume"], "taker_buy_base_volume"
        ),
        "taker_buy_quote_volume": _parse_decimal(
            row["taker_buy_quote_volume"], "taker_buy_quote_volume"
        ),
        "data_source": _required_text(row, "data_source"),
        "source_file": _optional_text(row, "source_file"),
        "checksum": _optional_text(row, "checksum"),
    }

    _validate_market_candle(normalized)
    return normalized


def _validate_and_sort_market_candles(
    rows: Sequence[dict[str, object]],
) -> tuple[list[dict[str, object]], list[str]]:
    warnings: list[str] = []
    seen_keys: set[tuple[object, ...]] = set()
    input_keys = [_candle_sort_key(row) for row in rows]

    for row in rows:
        key = _candle_identity_key(row)
        if key in seen_keys:
            raise DatasetValidationError(f"duplicate candle key: {_key_to_text(key)}")
        seen_keys.add(key)

    if input_keys != sorted(input_keys):
        warnings.append(
            "source rows were sorted by venue, market_type, symbol, timeframe, close_time"
        )

    sorted_rows = sorted(rows, key=_candle_sort_key)
    _validate_missing_candles(sorted_rows)
    return list(sorted_rows), warnings


def _validate_market_candle(row: dict[str, object]) -> None:
    if row["schema_version"] != SCHEMA_VERSION:
        raise DatasetValidationError(f"unsupported schema_version: {row['schema_version']}")

    open_time = _as_datetime(row["open_time"])
    close_time = _as_datetime(row["close_time"])
    source_available_at = _as_datetime(row["source_available_at"])
    if close_time <= open_time:
        raise DatasetValidationError("close_time must be after open_time")
    if source_available_at < close_time:
        raise DatasetValidationError("source_available_at must be at or after close_time")

    open_price = _as_decimal(row["open"])
    high = _as_decimal(row["high"])
    low = _as_decimal(row["low"])
    close = _as_decimal(row["close"])
    if min(open_price, high, low, close) <= 0:
        raise DatasetValidationError("OHLC prices must be positive")
    if high < low:
        raise DatasetValidationError("high must be greater than or equal to low")
    if high < max(open_price, close):
        raise DatasetValidationError("high must cover open and close")
    if low > min(open_price, close):
        raise DatasetValidationError("low must cover open and close")

    non_negative_decimal_fields = (
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    )
    for field_name in non_negative_decimal_fields:
        if _as_decimal(row[field_name]) < 0:
            raise DatasetValidationError(f"{field_name} must be non-negative")
    if _as_int(row["number_of_trades"]) < 0:
        raise DatasetValidationError("number_of_trades must be non-negative")

    candle_range = high - low
    body_reference = max(abs(open_price), Decimal("1"))
    if candle_range / body_reference > MAX_CANDLE_RANGE_TO_OPEN_RATIO:
        raise DatasetValidationError("abnormal wick exceeds 100% of reference price")


def _validate_missing_candles(rows: Sequence[dict[str, object]]) -> None:
    previous_by_group: dict[tuple[object, ...], dict[str, object]] = {}
    for row in rows:
        group_key = (row["venue"], row["market_type"], row["symbol"], row["timeframe"])
        previous = previous_by_group.get(group_key)
        if previous is not None:
            previous_close_time = _as_datetime(previous["close_time"])
            expected_close = previous_close_time + _timeframe_delta(str(row["timeframe"]))
            if _as_datetime(row["close_time"]) != expected_close:
                raise DatasetValidationError(
                    f"missing candle between {_format_timestamp(previous_close_time)} "
                    f"and {_format_timestamp(_as_datetime(row['close_time']))}"
                )
        previous_by_group[group_key] = row


def _write_market_candles(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable_rows = [
        {column: _to_arrow_value(row[column]) for column in MARKET_CANDLE_COLUMNS if column in row}
        for row in rows
    ]
    table = pa.Table.from_pylist(serializable_rows)
    pq.write_table(table, path)


def _write_manifest(manifest: DatasetManifest, source_csv: Path) -> None:
    manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(manifest)
    payload["raw_path"] = str(manifest.raw_path)
    payload["cleaned_path"] = str(manifest.cleaned_path)
    payload["manifest_path"] = str(manifest.manifest_path)
    payload["source"] = {
        "format": "csv",
        "path": str(source_csv),
    }
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


def _required_text(row: dict[str, str], field_name: str) -> str:
    value = row[field_name].strip()
    if not value:
        raise DatasetValidationError(f"{field_name} must not be empty")
    return value


def _optional_text(row: dict[str, str], field_name: str) -> str | None:
    value = row.get(field_name, "").strip()
    return value or None


def _parse_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DatasetValidationError(f"{field_name} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise DatasetValidationError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _parse_decimal(value: str, field_name: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise DatasetValidationError(f"{field_name} must be numeric") from error


def _parse_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise DatasetValidationError(f"{field_name} must be an integer") from error


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)!r}")
    return value


def _as_decimal(value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"expected Decimal, got {type(value)!r}")
    return value


def _as_int(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError(f"expected int, got {type(value)!r}")
    return value


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _timeframe_delta(timeframe: str) -> timedelta:
    match = re.fullmatch(r"(\d+)([mhd])", timeframe)
    if match is None:
        raise DatasetValidationError(f"unsupported timeframe: {timeframe}")

    quantity = int(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return timedelta(minutes=quantity)
    if unit == "h":
        return timedelta(hours=quantity)
    return timedelta(days=quantity)


def _candle_identity_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        row["open_time"],
        row["close_time"],
    )


def _candle_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        row["close_time"],
    )


def _key_to_text(key: Iterable[object]) -> str:
    return "|".join(str(part) for part in key)


def _to_arrow_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--generator-version", required=True)
    parser.add_argument("--generated-at", help="Optional RFC3339 timestamp for deterministic runs.")
    return parser.parse_args()


def main() -> None:
    args = _parse_cli_args()
    generated_at = (
        _parse_timestamp(args.generated_at, "generated_at") if args.generated_at else None
    )
    manifest = generate_market_dataset(
        MarketDatasetConfig(
            source_csv=args.source_csv,
            output_dir=args.output_dir,
            dataset_name=args.dataset_name,
            generator_version=args.generator_version,
            generated_at=generated_at,
        )
    )
    print(manifest.manifest_path)


if __name__ == "__main__":
    main()
