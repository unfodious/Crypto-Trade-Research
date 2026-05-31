"""Build research dataset manifests from Binance Data Vision spot klines."""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

import pyarrow as pa
import pyarrow.parquet as pq

SUPPORTED_PERIODS = frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"})


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    number_of_trades: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float


def build_spot_klines_dataset(
    *,
    symbols: list[str],
    start: datetime,
    end: datetime,
    period: str,
    dataset_name: str,
    output_dir: Path,
    cache_dir: Path,
) -> Path:
    rows: list[dict[str, object]] = []
    missing: list[str] = []

    for symbol in symbols:
        symbol_rows: list[Candle] = []
        for year, month in _months_between(start, end):
            try:
                symbol_rows.extend(
                    _read_monthly_zip(
                        symbol,
                        _download_monthly_zip(symbol, period, year, month, cache_dir),
                        start,
                        end,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - dataset builder reports all missing slices.
                missing.append(f"{symbol} {year}-{month:02d}: {exc}")
        symbol_rows.sort(key=lambda item: item.close_time)
        rows.extend(asdict(item) for item in symbol_rows)

    rows.sort(key=lambda item: (item["symbol"], item["close_time"]))
    dataset_dir = output_dir / dataset_name
    clean_path = dataset_dir / "clean" / "market_candles.parquet"
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), clean_path)

    manifest_path = dataset_dir / "manifest.json"
    manifest = {
        "schema_version": "research.dataset.v1",
        "dataset_name": dataset_name,
        "source": f"binance-data-vision-spot-monthly-klines-{period}",
        "market_type": "spot",
        "symbols": symbols,
        "period": period,
        "start": _format_timestamp(start),
        "end": _format_timestamp(end),
        "row_count": len(rows),
        "cleaned_path": str(clean_path),
        "missing": missing,
        "generated_at": _format_timestamp(datetime.now(UTC)),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path


def _download_monthly_zip(
    symbol: str,
    period: str,
    year: int,
    month: int,
    cache_dir: Path,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{symbol}-{period}-{year}-{month:02d}.zip"
    if path.exists() and path.stat().st_size > 0:
        return path

    url = (
        "https://data.binance.vision/data/spot/monthly/klines/"
        f"{symbol}/{period}/{symbol}-{period}-{year}-{month:02d}.zip"
    )
    with urlopen(url, timeout=60) as response:
        path.write_bytes(response.read())
    return path


def _read_monthly_zip(symbol: str, path: Path, start: datetime, end: datetime) -> list[Candle]:
    rows: list[Candle] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not names:
            return rows
        with archive.open(names[0]) as file:
            for raw_line in file:
                fields = raw_line.decode("utf-8").strip().split(",")
                if len(fields) < 7 or not fields[0].isdigit():
                    continue
                open_time = _binance_timestamp(fields[0])
                close_time = _binance_timestamp(fields[6]) + timedelta(microseconds=1)
                if close_time <= start or open_time >= end:
                    continue
                rows.append(
                    Candle(
                        symbol=symbol,
                        open_time=open_time,
                        close_time=close_time,
                        open=float(fields[1]),
                        high=float(fields[2]),
                        low=float(fields[3]),
                        close=float(fields[4]),
                        volume=float(fields[5]),
                        quote_volume=_optional_float_field(fields, 7),
                        number_of_trades=_optional_int_field(fields, 8),
                        taker_buy_base_volume=_optional_float_field(fields, 9),
                        taker_buy_quote_volume=_optional_float_field(fields, 10),
                    )
                )
    return rows


def _optional_float_field(fields: list[str], index: int) -> float:
    return float(fields[index]) if len(fields) > index and fields[index] else 0.0


def _optional_int_field(fields: list[str], index: int) -> int:
    return int(fields[index]) if len(fields) > index and fields[index] else 0


def _binance_timestamp(value: str) -> datetime:
    timestamp = int(value)
    divisor = 1_000_000 if timestamp > 10_000_000_000_000 else 1_000
    return datetime.fromtimestamp(timestamp / divisor, tz=UTC)


def _months_between(start: datetime, end: datetime) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    current = datetime(start.year, start.month, 1, tzinfo=UTC)
    while current < end:
        months.append((current.year, current.month))
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1, tzinfo=UTC)
        else:
            current = datetime(current.year, current.month + 1, 1, tzinfo=UTC)
    return months


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", required=True, help="Comma-separated Binance spot symbols.")
    parser.add_argument(
        "--period",
        default="1h",
        choices=sorted(SUPPORTED_PERIODS),
        help="Binance Data Vision spot klines period.",
    )
    parser.add_argument("--start", required=True, help="Inclusive ISO timestamp.")
    parser.add_argument("--end", required=True, help="Exclusive ISO timestamp.")
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/generated"))
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/generated/binance_spot_klines_cache"),
    )
    args = parser.parse_args()
    manifest_path = build_spot_klines_dataset(
        symbols=[symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()],
        start=_parse_timestamp(args.start),
        end=_parse_timestamp(args.end),
        period=args.period,
        dataset_name=args.dataset_name,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
