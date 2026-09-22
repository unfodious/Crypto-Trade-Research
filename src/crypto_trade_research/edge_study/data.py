"""Load Binance USD-M 1m klines from the local archive and resample them.

The archive under `backend/storage/historical_data/um_futures/<PAIR>/1m/` holds
Binance public-data CSVs (monthly for the majors, daily for the alts). We read
1m only and build every higher timeframe ourselves, so all pairs get bars that
are constructed identically regardless of which archives exist for them.

The 1m series is also kept because the triple-barrier labeller resolves barrier
order on the 1m path: inside a single 4h bar the OHLC alone cannot say whether
the stop or the target was touched first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger(__name__)

DEFAULT_ARCHIVE = Path("../backend/storage/historical_data/um_futures")

COLUMNS = [
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

KEEP = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "count",
    "taker_buy_quote_volume",
]

RESAMPLE_RULES = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "quote_volume": "sum",
    "count": "sum",
    "taker_buy_quote_volume": "sum",
}


@dataclass(frozen=True)
class PairData:
    """One pair's bars. `minute` is the raw 1m series used for barrier paths."""

    pair: str
    minute: pd.DataFrame
    bars: dict[str, pd.DataFrame]


def _read_one(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, header=0, names=COLUMNS, dtype={"open_time": "int64"})
    # Some Binance archives repeat the header as a data row; drop anything unparseable.
    frame = frame[pd.to_numeric(frame["open"], errors="coerce").notna()]
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce").astype("int64")
    for column in KEEP:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[["open_time", *KEEP]]


def load_minutes(pair: str, archive: Path, start: str, end: str) -> pd.DataFrame:
    """Read every 1m CSV for `pair` and return a de-duplicated, sorted frame."""
    directory = archive / pair / "1m"
    files = sorted(directory.glob(f"{pair}-1m-*.csv"))
    if not files:
        raise FileNotFoundError(f"no 1m CSVs for {pair} under {directory}")
    frames = [_read_one(path) for path in files]
    minute = pd.concat(frames, ignore_index=True)
    minute["open_time"] = pd.to_datetime(minute["open_time"], unit="ms", utc=True)
    minute = (
        minute.drop_duplicates(subset="open_time", keep="last")
        .sort_values("open_time")
        .set_index("open_time")
    )
    return minute.loc[str(start) : str(end)]


def resample(minute: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate 1m bars into `timeframe` bars, left-labelled and left-closed.

    A bar labelled 04:00 on a 4h grid covers [04:00, 08:00) and is only complete
    once 08:00 has passed. Callers must therefore treat the bar label as the
    bar's OPEN time and use the bar only after it closed.
    """
    bars = minute.resample(timeframe, label="left", closed="left").agg(RESAMPLE_RULES)
    return bars.dropna(subset=["open", "high", "low", "close"])


def load_pair(
    pair: str,
    archive: Path,
    start: str,
    end: str,
    timeframes: tuple[str, ...] = ("4h", "1D"),
    cache_dir: Path | None = None,
) -> PairData:
    """Load one pair, using a parquet cache when one is available."""
    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{pair}_1m_{start}_{end}.parquet"
    if cache_path is not None and cache_path.exists():
        minute = pd.read_parquet(cache_path)
    else:
        minute = load_minutes(pair, archive, start, end)
        if cache_path is not None:
            minute.to_parquet(cache_path)
    bars = {timeframe: resample(minute, timeframe) for timeframe in timeframes}
    LOGGER.info("%s: %d 1m bars, %s", pair, len(minute), {k: len(v) for k, v in bars.items()})
    return PairData(pair=pair, minute=minute, bars=bars)


def available_pairs(archive: Path) -> list[str]:
    return sorted(path.name for path in archive.iterdir() if (path / "1m").is_dir())
