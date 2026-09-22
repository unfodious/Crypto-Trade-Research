"""Non-price (crowding and positioning) inputs for the 4h edge study.

Research only. Every endpoint used here is public and unauthenticated; this
module has no credentials and no order path.

What is joined, and on whose clock
----------------------------------

Price features live on the 4h decision grid (`decision_time` = the 4h bar's
close). The inputs below live on their own clocks and are published with their
own lags, so each one carries an explicit `known_at` column and is joined with
`merge_asof(direction="backward")` against `decision_time` - exactly the way
`features.build_features` already joins the 1d and BTC grids. Nothing can be
visible in a feature row before `known_at`.

| input | native clock | `known_at` | source |
|---|---|---|---|
| funding rate | 8h settlements | settlement instant | `fapi/v1/fundingRate` |
| open interest + long/short ratios | 5m snapshots | snapshot + 5m | Data Vision `daily/metrics` |
| book depth (+/-1..5%) | 30s snapshots -> 5m means | snapshot + 1m | Data Vision `bookDepth` |
| liquidations | - | - | not available (see below) |

**Funding.** A settlement's realized rate is only final at the settlement
instant, so `known_at = funding_time`. The *predicted* rate streams
continuously before that, but it is not in any historical archive, so using the
settled value at its settlement is both correct and conservative.

**Open interest.** Binance's `openInterestHist` snapshots are stamped
`create_time` and queryable within a few seconds. The daily archive publishes
the same rows. `known_at = create_time + 5m` (one full snapshot interval) is a
deliberate over-estimate of the lag: at 4h decision spacing it costs nothing and
it cannot flatter the study.

**Book depth.** 30-second snapshots reduced to 5-minute means before anything
else touches them, so the panel is ~288 rows/day/pair instead of 2,880.
`known_at = window_end + 1m`.

**Liquidations are NOT included, and this is a data limitation, not a choice.**
`research/.../data/binance_liquidations.py` is a *live websocket recorder*
(`!forceOrder@arr`); it can only collect forward from the moment it is started.
Binance retired the `liquidationSnapshot` Data Vision archive - probed at
2024-07-01, 2025-06-01, daily and monthly, all 404 - and `fapi` exposes no
historical forced-order endpoint. Every remaining source (Coinglass, Coinalyze)
is credentialed and/or paid, which this study is not allowed to use. What is
included instead is an explicitly named *proxy*, `liq_pressure_long/short`,
built from the one observable that forced deleveraging always leaves behind: a
sharp drop in open interest concurrent with an adverse price move. It is a
proxy and is labelled as one; it is not a liquidation feed.
"""

from __future__ import annotations

import io
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_trade_research.data.binance_book_depth import (
    DATA_VISION_BASE_URL,
    EXPECTED_PERCENTAGES,
)
from crypto_trade_research.data.funding import BINANCE_FUNDING_RATE_URL

LOGGER = logging.getLogger(__name__)

USER_AGENT = "crypto-trade-research/edge-study-altdata"

#: Publication lags applied to each source's native timestamp. Deliberately
#: generous: at 4h decision spacing an extra few minutes costs no information
#: and removes any argument about snapshot availability.
FUNDING_LAG = timedelta(0)
METRICS_LAG = timedelta(minutes=5)
DEPTH_LAG = timedelta(minutes=1)

#: The panel grid the 5m/30s sources are reduced to before feature maths.
PANEL_FREQ = "5min"
PANELS_PER_HOUR = 12


class AltDataError(RuntimeError):
    """Raised when an alt-data source cannot be ingested."""


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------


def _get(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return bytes(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise FileNotFoundError(url) from error
        raise


def _zip_csv(payload: bytes, url: str) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise AltDataError(f"archive must contain exactly one CSV: {url}")
        with archive.open(names[0]) as handle:
            return pd.read_csv(handle)


def _days(start: str, end: str) -> list[date]:
    first = pd.Timestamp(start).date()
    last = pd.Timestamp(end).date()
    span = (last - first).days
    return [first + timedelta(days=offset) for offset in range(span + 1)]


# ---------------------------------------------------------------------------
# funding
# ---------------------------------------------------------------------------


def fetch_funding(pair: str, start: str, end: str) -> pd.DataFrame:
    """Settled 8h funding rates for one pair, keyed by `known_at`."""
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    rows: list[dict[str, object]] = []
    cursor = start_ms
    while cursor < end_ms:
        query = urllib.parse.urlencode(
            {"symbol": pair, "startTime": cursor, "endTime": end_ms, "limit": 1000}
        )
        payload = json.loads(_get(f"{BINANCE_FUNDING_RATE_URL}?{query}").decode("utf-8"))
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        last = int(payload[-1]["fundingTime"])
        if last <= cursor:
            break
        cursor = last + 1
        if len(payload) < 1000:
            break
    if not rows:
        raise AltDataError(f"no funding rows for {pair}")
    frame = pd.DataFrame(rows)
    frame["funding_time"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    frame["funding_rate"] = frame["fundingRate"].astype(float)
    frame = (
        frame[["funding_time", "funding_rate"]]
        .drop_duplicates(subset="funding_time", keep="last")
        .sort_values("funding_time")
        .reset_index(drop=True)
    )
    frame["known_at"] = frame["funding_time"] + FUNDING_LAG
    return frame


# ---------------------------------------------------------------------------
# open interest / long-short ratios (Data Vision daily "metrics")
# ---------------------------------------------------------------------------

METRIC_FIELDS = (
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)


def _metrics_url(pair: str, day: date, base_url: str) -> str:
    return f"{base_url}/data/futures/um/daily/metrics/{pair}/{pair}-metrics-{day.isoformat()}.zip"


def _metrics_day(pair: str, day: date, base_url: str) -> pd.DataFrame | None:
    url = _metrics_url(pair, day, base_url)
    try:
        frame = _zip_csv(_get(url), url)
    except FileNotFoundError:
        return None
    frame["metrics_time"] = pd.to_datetime(frame["create_time"], utc=True)
    for column in METRIC_FIELDS:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    return frame[["metrics_time", *METRIC_FIELDS]]


def fetch_metrics(
    pair: str,
    start: str,
    end: str,
    base_url: str = DATA_VISION_BASE_URL,
    workers: int = 12,
) -> pd.DataFrame:
    """5m open-interest and long/short-ratio snapshots, keyed by `known_at`."""
    days = _days(start, end)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        parts = list(pool.map(lambda day: _metrics_day(pair, day, base_url), days))
    frames = [part for part in parts if part is not None and not part.empty]
    missing = len(days) - len(frames)
    if not frames:
        raise AltDataError(f"no metrics files for {pair}")
    if missing:
        LOGGER.warning("%s metrics: %d/%d days missing", pair, missing, len(days))
    panel = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset="metrics_time", keep="last")
        .sort_values("metrics_time")
        .reset_index(drop=True)
    )
    panel["known_at"] = panel["metrics_time"] + METRICS_LAG
    return panel


# ---------------------------------------------------------------------------
# book depth (Data Vision daily "bookDepth")
# ---------------------------------------------------------------------------

DEPTH_LEVELS = tuple(level for level in EXPECTED_PERCENTAGES if level > 0)


def _depth_url(pair: str, day: date, base_url: str) -> str:
    return (
        f"{base_url}/data/futures/um/daily/bookDepth/{pair}/{pair}-bookDepth-{day.isoformat()}.zip"
    )


def _depth_day(pair: str, day: date, base_url: str) -> pd.DataFrame | None:
    """Reduce one day of 30s depth snapshots to 5m means.

    The reduction happens here, on the raw bytes, so 3.4 GB of daily archives
    never lands on disk and never enters the study's memory footprint.
    """
    url = _depth_url(pair, day, base_url)
    try:
        frame = _zip_csv(_get(url), url)
    except FileNotFoundError:
        return None
    if frame.empty:
        return None
    frame["depth_time"] = pd.to_datetime(frame["timestamp"], utc=True)
    # Some daily archives carry fractional or out-of-spec percentage bands.
    # Keep only the documented +/-1..5% levels rather than rounding strays into
    # a neighbouring band, which would silently corrupt the imbalance ratios.
    frame["percentage"] = pd.to_numeric(frame["percentage"], errors="coerce")
    frame["notional"] = pd.to_numeric(frame["notional"], errors="coerce")
    frame = frame.dropna(subset=["percentage", "notional"])
    frame = frame[frame["percentage"].isin(EXPECTED_PERCENTAGES)]
    if frame.empty:
        return None
    frame["percentage"] = frame["percentage"].astype("int64")
    wide = frame.pivot_table(
        index="depth_time", columns="percentage", values="notional", aggfunc="last"
    )
    columns: dict[str, pd.Series] = {}
    for level in DEPTH_LEVELS:
        if level in wide.columns:
            columns[f"ask_notional_{level}pct"] = wide[level]
        if -level in wide.columns:
            columns[f"bid_notional_{level}pct"] = wide[-level]
    if not columns:
        return None
    reduced = pd.DataFrame(columns).resample(PANEL_FREQ, label="right", closed="right").mean()
    return reduced.dropna(how="all").reset_index()


def fetch_book_depth(
    pair: str,
    start: str,
    end: str,
    base_url: str = DATA_VISION_BASE_URL,
    workers: int = 12,
) -> pd.DataFrame:
    """5m-mean book depth within +/-1..5% of mid, keyed by `known_at`."""
    days = _days(start, end)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        parts = list(pool.map(lambda day: _depth_day(pair, day, base_url), days))
    frames = [part for part in parts if part is not None and not part.empty]
    missing = len(days) - len(frames)
    if not frames:
        raise AltDataError(f"no book-depth files for {pair}")
    if missing:
        LOGGER.warning("%s bookDepth: %d/%d days missing", pair, missing, len(days))
    panel = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset="depth_time", keep="last")
        .sort_values("depth_time")
        .reset_index(drop=True)
    )
    panel["known_at"] = panel["depth_time"] + DEPTH_LAG
    return panel


# ---------------------------------------------------------------------------
# cached panel assembly
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AltPanels:
    """One pair's non-price panels, each already carrying `known_at`."""

    pair: str
    funding: pd.DataFrame
    metrics: pd.DataFrame
    depth: pd.DataFrame


def load_panels(
    pair: str,
    start: str,
    end: str,
    cache_dir: Path | None,
    base_url: str = DATA_VISION_BASE_URL,
    allow_missing: bool = True,
) -> AltPanels:
    """Load (and cache) the three panels for one pair.

    A missing source degrades to an empty panel when `allow_missing`, so a pair
    without depth archives still contributes its funding and OI features rather
    than dropping out of the universe.
    """
    loaders = {
        "funding": lambda: fetch_funding(pair, start, end),
        "metrics": lambda: fetch_metrics(pair, start, end, base_url),
        "depth": lambda: fetch_book_depth(pair, start, end, base_url),
    }
    panels: dict[str, pd.DataFrame] = {}
    for kind, loader in loaders.items():
        path = None
        if cache_dir is not None:
            path = cache_dir / kind / f"{pair}_{start}_{end}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
        if path is not None and path.exists():
            panels[kind] = pd.read_parquet(path)
            continue
        try:
            frame = loader()
        except (AltDataError, OSError) as error:
            if not allow_missing:
                raise
            LOGGER.warning("%s %s unavailable: %s", pair, kind, error)
            frame = pd.DataFrame(columns=["known_at"])
        if path is not None:
            frame.to_parquet(path)
        panels[kind] = frame
        LOGGER.info("%s %s: %d rows", pair, kind, len(frame))
    return AltPanels(
        pair=pair, funding=panels["funding"], metrics=panels["metrics"], depth=panels["depth"]
    )


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------


def _trailing_z(series: pd.Series, window: int) -> pd.Series:
    """Trailing z-score. Same contract as `indicators.zscore`: no future rows."""
    mean = series.rolling(window, min_periods=max(10, window // 4)).mean()
    std = series.rolling(window, min_periods=max(10, window // 4)).std(ddof=0)
    return (series - mean) / std.replace(0.0, np.nan)


def funding_features(funding: pd.DataFrame) -> pd.DataFrame:
    """Per-settlement funding features on the funding clock."""
    if funding.empty:
        return pd.DataFrame(columns=["known_at", *FUNDING_FEATURES])
    frame = funding.sort_values("known_at").reset_index(drop=True)
    rate = frame["funding_rate"]
    out = pd.DataFrame({"known_at": frame["known_at"]})
    out["fund_rate"] = rate
    out["fund_rate_mean_3d"] = rate.rolling(9, min_periods=3).mean()
    out["fund_rate_cum_7d"] = rate.rolling(21, min_periods=7).sum()
    out["fund_rate_z"] = _trailing_z(rate, 90)
    return out


def metrics_features(metrics: pd.DataFrame) -> pd.DataFrame:
    """Open-interest and crowd-positioning features on the 5m metrics clock."""
    if metrics.empty:
        return pd.DataFrame(columns=["known_at", *METRICS_FEATURES, "open_interest"])
    frame = metrics.sort_values("known_at").reset_index(drop=True)
    log_oi = np.log(frame["sum_open_interest"].replace(0.0, np.nan))
    out = pd.DataFrame({"known_at": frame["known_at"]})
    out["open_interest"] = frame["sum_open_interest"]
    out["oi_change_4h"] = log_oi.diff(4 * PANELS_PER_HOUR)
    out["oi_change_1d"] = log_oi.diff(24 * PANELS_PER_HOUR)
    # 30 days of 5m rows; long enough that the z-score describes a regime, not a day.
    out["oi_change_z"] = _trailing_z(out["oi_change_4h"], 30 * 24 * PANELS_PER_HOUR)
    out["ls_top_position"] = frame["sum_toptrader_long_short_ratio"]
    out["ls_global_account_z"] = _trailing_z(
        frame["count_long_short_ratio"], 7 * 24 * PANELS_PER_HOUR
    )
    out["taker_ls_volume"] = frame["sum_taker_long_short_vol_ratio"]
    return out


def depth_features(depth: pd.DataFrame) -> pd.DataFrame:
    """Order-book shape features on the 5m depth clock."""
    if depth.empty:
        return pd.DataFrame(columns=["known_at", *DEPTH_FEATURES])
    frame = depth.sort_values("known_at").reset_index(drop=True)
    out = pd.DataFrame({"known_at": frame["known_at"]})
    for level in (1, 5):
        bid = frame.get(f"bid_notional_{level}pct")
        ask = frame.get(f"ask_notional_{level}pct")
        if bid is None or ask is None:
            out[f"depth_imbalance_{level}pct"] = np.nan
            continue
        total = (bid + ask).replace(0.0, np.nan)
        out[f"depth_imbalance_{level}pct"] = (bid - ask) / total
    near = frame.get("bid_notional_1pct", pd.Series(np.nan, index=frame.index)) + frame.get(
        "ask_notional_1pct", pd.Series(np.nan, index=frame.index)
    )
    far = frame.get("bid_notional_5pct", pd.Series(np.nan, index=frame.index)) + frame.get(
        "ask_notional_5pct", pd.Series(np.nan, index=frame.index)
    )
    out["depth_concentration"] = near / far.replace(0.0, np.nan)
    # 7 days of 5m rows: depth has a strong weekly/daily seasonal, so the level
    # itself is useless and only the trailing-standardised level is comparable.
    depth_window = 7 * 24 * PANELS_PER_HOUR
    out["depth_notional_z"] = _trailing_z(np.log(far.replace(0.0, np.nan)), depth_window)
    return out


FUNDING_FEATURES = ("fund_rate", "fund_rate_mean_3d", "fund_rate_cum_7d", "fund_rate_z")
METRICS_FEATURES = (
    "oi_change_4h",
    "oi_change_1d",
    "oi_change_z",
    "ls_top_position",
    "ls_global_account_z",
    "taker_ls_volume",
)
DEPTH_FEATURES = (
    "depth_imbalance_1pct",
    "depth_imbalance_5pct",
    "depth_concentration",
    "depth_notional_z",
)
#: Derived on the 4h grid from joined OI plus the bar's own return; see the
#: module docstring on why this is a proxy and not a liquidation feed.
LIQUIDATION_PROXY_FEATURES = ("liq_pressure_long", "liq_pressure_short")

ALT_FEATURE_COLUMNS: tuple[str, ...] = (
    *FUNDING_FEATURES,
    *METRICS_FEATURES,
    *DEPTH_FEATURES,
    *LIQUIDATION_PROXY_FEATURES,
)


def _asof_join(base: pd.DataFrame, panel: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Backward `merge_asof` of `panel` onto `base.decision_time` via `known_at`.

    This is the single place where a non-price value becomes visible to a
    decision row, and it is a backward join on the data's own known-at time.
    `direction="backward"` with `allow_exact_matches=True` means a value stamped
    exactly at the decision instant is usable and anything later is not.
    """
    columns = list(columns)
    if panel.empty:
        for column in columns:
            base[column] = np.nan
        return base
    right = panel[["known_at", *[c for c in columns if c in panel.columns]]].sort_values("known_at")
    for column in columns:
        if column not in right.columns:
            right[column] = np.nan
    merged = pd.merge_asof(
        base.sort_values("decision_time"),
        right,
        left_on="decision_time",
        right_on="known_at",
        direction="backward",
        allow_exact_matches=True,
    )
    return merged.drop(columns=["known_at"])


def attach_alt_features(frame: pd.DataFrame, panels: AltPanels | None) -> pd.DataFrame:
    """Join every non-price feature onto a 4h feature frame.

    `frame` is the output of `features.build_features`: indexed by 4h bar open
    time and carrying `decision_time`. The result has the same index and the
    same row order, plus `ALT_FEATURE_COLUMNS`.
    """
    index = frame.index
    if panels is None:
        for column in ALT_FEATURE_COLUMNS:
            frame[column] = np.nan
        return frame

    base = frame.reset_index(names="_bar_time")
    base = _asof_join(base, funding_features(panels.funding), FUNDING_FEATURES)
    base = _asof_join(base, metrics_features(panels.metrics), (*METRICS_FEATURES, "open_interest"))
    base = _asof_join(base, depth_features(panels.depth), DEPTH_FEATURES)
    base = base.sort_values("_bar_time").set_index("_bar_time")
    base.index = index
    base.index.name = frame.index.name

    # Liquidation proxy. A forced-liquidation cascade is open interest falling
    # hard WHILE price moves against the crowd; either alone is ordinary flow.
    # Both legs use only values already joined causally above plus the bar's own
    # closed return, so the proxy inherits the same known-at guarantee.
    oi_drop = (-base["oi_change_4h"]).clip(lower=0.0)
    bar_return = base["return_1"] if "return_1" in base.columns else pd.Series(np.nan, base.index)
    base["liq_pressure_long"] = oi_drop * (-bar_return).clip(lower=0.0)
    base["liq_pressure_short"] = oi_drop * bar_return.clip(lower=0.0)
    if "open_interest" in base.columns:
        base = base.drop(columns=["open_interest"])
    return base


def main(argv: list[str] | None = None) -> int:
    """Warm the alt-data cache without running the study."""
    import argparse

    parser = argparse.ArgumentParser(description="Download alt-data panels (research only).")
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/generated/altdata-cache"))
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for pair in (p.strip() for p in arguments.pairs.split(",") if p.strip()):
        panels = load_panels(pair, arguments.start, arguments.end, arguments.cache_dir)
        LOGGER.info(
            "%s ready: funding=%d metrics=%d depth=%d",
            pair,
            len(panels.funding),
            len(panels.metrics),
            len(panels.depth),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
