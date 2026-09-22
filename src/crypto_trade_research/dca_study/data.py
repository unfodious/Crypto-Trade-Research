"""Daily spot close series for the DCA study.

The user buys **spot**, so the study uses Binance **spot** daily klines rather
than the USD-M perp archive that the edge study reads. That also buys history:
the local perp archive starts 2023-12 (BTC/ETH/SOL) or 2024-07 (everything
else), while spot 1d goes back to 2017-08 for BTC and ETH. A monthly-cadence
question needs decades-of-purchases, not 23 of them.

Source: Binance public data (`https://data.binance.vision`), monthly 1d kline
zips. Downloads are cached as parquet under `data/generated/dca-study-cache/`,
which is gitignored. Nothing is re-downloaded once cached.

The edge-study package is read-only for this module: we do not import or modify
it. A local-archive fallback is provided for offline runs.
"""

from __future__ import annotations

import io
import logging
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
DEFAULT_CACHE = Path("data/generated/dca-study-cache")

# Same 11-pair universe as the edge study, so the two reports are comparable.
UNIVERSE = [
    "BTCUSDT",
    "ETHUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "SOLUSDT",
    "DOTUSDT",
    "AVAXUSDT",
    "ATOMUSDT",
    "SUIUSDT",
    "TONUSDT",
    "ICPUSDT",
]

MAJORS = ["BTCUSDT", "ETHUSDT"]

KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]


@dataclass(frozen=True)
class Series:
    """A daily close series for one symbol."""

    symbol: str
    frame: pd.DataFrame  # DatetimeIndex (daily, UTC-naive), column "close"

    @property
    def close(self) -> pd.Series:
        return self.frame["close"]

    @property
    def start(self) -> pd.Timestamp:
        return self.frame.index[0]

    @property
    def end(self) -> pd.Timestamp:
        return self.frame.index[-1]


def _month_iter(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def _parse_month_csv(raw: bytes) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(raw), header=None, names=KLINE_COLUMNS)
    # Binance switched some archives to a header row; drop it if present.
    frame = frame[pd.to_numeric(frame["open_time"], errors="coerce").notna()]
    open_time = pd.to_numeric(frame["open_time"])
    # Archives mix millisecond and microsecond epochs.
    unit = "us" if open_time.max() > 1e15 else "ms"
    index = pd.to_datetime(open_time, unit=unit)
    out = pd.DataFrame({"close": pd.to_numeric(frame["close"]).to_numpy()}, index=index)
    out.index = out.index.normalize()
    out.index.name = "date"
    return out


def _download_month(symbol: str, year: int, month: int) -> pd.DataFrame | None:
    name = f"{symbol}-1d-{year:04d}-{month:02d}"
    url = f"{BASE_URL}/{symbol}/1d/{name}.zip"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - public archive
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        raw = archive.read(archive.namelist()[0])
    return _parse_month_csv(raw)


def load_daily_spot(
    symbol: str,
    *,
    cache_dir: Path | str = DEFAULT_CACHE,
    first_month: date = date(2017, 8, 1),
    last_month: date | None = None,
    allow_download: bool = True,
) -> Series:
    """Return the cached (or freshly downloaded) daily spot close series."""

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{symbol}_1d_spot.parquet"

    if cache_path.exists():
        frame = pd.read_parquet(cache_path)
        return Series(symbol=symbol, frame=frame)

    if not allow_download:
        raise FileNotFoundError(f"no cached series for {symbol} at {cache_path}")

    last_month = last_month or date.today()
    parts: list[pd.DataFrame] = []
    misses_after_first_hit = 0
    for year, month in _month_iter(first_month, last_month):
        part = _download_month(symbol, year, month)
        if part is None:
            if parts:
                misses_after_first_hit += 1
                # Two consecutive gaps past the last available month: stop.
                if misses_after_first_hit >= 2:
                    break
            continue
        misses_after_first_hit = 0
        parts.append(part)

    if not parts:
        raise RuntimeError(f"no spot 1d archives found for {symbol}")

    frame = pd.concat(parts).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame.to_parquet(cache_path)
    LOGGER.info(
        "cached %s: %s .. %s (%d days)", symbol, frame.index[0], frame.index[-1], len(frame)
    )
    return Series(symbol=symbol, frame=frame)


def load_universe(
    symbols: list[str] | None = None,
    *,
    cache_dir: Path | str = DEFAULT_CACHE,
    allow_download: bool = True,
) -> dict[str, Series]:
    out: dict[str, Series] = {}
    for symbol in symbols or UNIVERSE:
        try:
            out[symbol] = load_daily_spot(
                symbol, cache_dir=cache_dir, allow_download=allow_download
            )
        except Exception as exc:  # pragma: no cover - network / archive shape
            LOGGER.warning("skipping %s: %s", symbol, exc)
    return out
