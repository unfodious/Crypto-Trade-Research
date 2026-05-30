"""Build selected-trade futures metrics features for fast research screens."""

from __future__ import annotations

import argparse
import bisect
import json
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

KEY_COLUMNS = ("symbol", "timeframe", "decision_time")
METRICS_COLUMNS = (
    "symbol",
    "metrics_time",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
RATIO_COLUMNS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
KNOWN_SYMBOLS = (
    "ADAUSDT",
    "ATOMUSDT",
    "AVAXUSDT",
    "BTCUSDT",
    "DOTUSDT",
    "ETHUSDT",
    "ICPUSDT",
    "SOLUSDT",
    "SUIUSDT",
    "TONUSDT",
    "XRPUSDT",
)
SYMBOL_GROUPS = {
    "fm_symbol_group_ada_icp_sui": frozenset({"ADAUSDT", "ICPUSDT", "SUIUSDT"}),
    "fm_symbol_group_avax_sol": frozenset({"AVAXUSDT", "SOLUSDT"}),
}


class FuturesMetricsSelectedFeaturesError(ValueError):
    """Raised when selected-trade futures metrics features cannot be built."""


@dataclass(frozen=True, slots=True)
class FuturesMetricsSelectedWindowConfig:
    name: str
    replay_report_path: Path
    output_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FuturesMetricsSelectedWindowConfig:
        return cls(
            name=str(payload["name"]),
            replay_report_path=Path(str(payload["replay_report_path"])),
            output_path=Path(str(payload["output_path"])),
        )


@dataclass(frozen=True, slots=True)
class FuturesMetricsSelectedFeaturesConfig:
    metrics_path: Path
    max_metrics_age_minutes: int
    windows: tuple[FuturesMetricsSelectedWindowConfig, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FuturesMetricsSelectedFeaturesConfig:
        return cls(
            metrics_path=Path(str(payload["metrics_path"])),
            max_metrics_age_minutes=int(payload.get("max_metrics_age_minutes", 10)),
            windows=tuple(
                FuturesMetricsSelectedWindowConfig.from_dict(dict(item))
                for item in payload["windows"]
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> FuturesMetricsSelectedFeaturesConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class _MetricsIndex:
    rows_by_symbol: dict[str, list[dict[str, object]]]
    times_by_symbol: dict[str, list[datetime]]
    market_medians_by_time: dict[datetime, dict[str, float]]
    max_age: timedelta


def build_futures_metrics_selected_features(
    config: FuturesMetricsSelectedFeaturesConfig,
) -> dict[str, object]:
    """Build per-window feature parquet files keyed by selected-trade decision rows."""

    if config.max_metrics_age_minutes <= 0:
        raise FuturesMetricsSelectedFeaturesError("max_metrics_age_minutes must be positive")
    metrics_index = _load_metrics_index(config.metrics_path, config.max_metrics_age_minutes)
    windows = []
    for window in config.windows:
        keys = _selected_trade_keys(window.replay_report_path)
        rows = [_feature_row(key, metrics_index) for key in keys]
        window.output_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), window.output_path)
        windows.append(
            {
                "name": window.name,
                "replay_report_path": str(window.replay_report_path),
                "output_path": str(window.output_path),
                "row_count": len(rows),
                "matched_metrics_count": sum(1 for row in rows if row["fm_metrics_match"] == 1),
            }
        )
    return {
        "metrics_path": str(config.metrics_path),
        "max_metrics_age_minutes": config.max_metrics_age_minutes,
        "windows": windows,
    }


def _load_metrics_index(metrics_path: Path, max_metrics_age_minutes: int) -> _MetricsIndex:
    if not metrics_path.exists():
        raise FuturesMetricsSelectedFeaturesError(f"missing metrics parquet: {metrics_path}")
    rows = [
        _normalize_metric_row(row)
        for row in pq.read_table(metrics_path, columns=list(METRICS_COLUMNS)).to_pylist()
    ]
    rows_by_symbol: dict[str, list[dict[str, object]]] = {}
    rows_by_time: dict[datetime, list[dict[str, object]]] = {}
    for row in rows:
        symbol = str(row["symbol"])
        metrics_time = _as_datetime(row["metrics_time"])
        rows_by_symbol.setdefault(symbol, []).append(row)
        rows_by_time.setdefault(metrics_time, []).append(row)

    times_by_symbol: dict[str, list[datetime]] = {}
    for symbol, symbol_rows in rows_by_symbol.items():
        symbol_rows.sort(key=lambda item: _as_datetime(item["metrics_time"]))
        times_by_symbol[symbol] = [_as_datetime(row["metrics_time"]) for row in symbol_rows]

    market_medians_by_time = {
        metrics_time: _market_medians(time_rows) for metrics_time, time_rows in rows_by_time.items()
    }
    return _MetricsIndex(
        rows_by_symbol=rows_by_symbol,
        times_by_symbol=times_by_symbol,
        market_medians_by_time=market_medians_by_time,
        max_age=timedelta(minutes=max_metrics_age_minutes),
    )


def _selected_trade_keys(replay_report_path: Path) -> list[dict[str, object]]:
    replay_report = _read_json(replay_report_path)
    keys: dict[tuple[object, ...], dict[str, object]] = {}
    for replay in replay_report["replays"]:
        selected_path = replay_report_path.parent / str(dict(replay)["trades_path"])
        if not selected_path.exists():
            raise FuturesMetricsSelectedFeaturesError(
                f"missing selected trades parquet: {selected_path}"
            )
        for row in pq.read_table(selected_path, columns=list(KEY_COLUMNS)).to_pylist():
            key = (
                str(row["symbol"]),
                str(row["timeframe"]),
                _as_datetime(row["decision_time"]),
            )
            keys[key] = {
                "symbol": key[0],
                "timeframe": key[1],
                "decision_time": key[2],
            }
    return sorted(keys.values(), key=lambda item: tuple(item[column] for column in KEY_COLUMNS))


def _feature_row(key: dict[str, object], metrics_index: _MetricsIndex) -> dict[str, object]:
    symbol = str(key["symbol"])
    decision_time = _as_datetime(key["decision_time"])
    current = _lookup_metric_row(symbol, decision_time, metrics_index)
    base = {
        "symbol": symbol,
        "timeframe": str(key["timeframe"]),
        "decision_time": decision_time,
        **_categorical_feature_flags(symbol, decision_time),
    }
    if current is None:
        return {
            **base,
            "fm_metrics_match": 0,
            "fm_metrics_age_minutes": None,
            "fm_sum_open_interest_value": None,
            "fm_oi_value_change_1h": None,
            "fm_oi_value_change_4h": None,
            "fm_count_toptrader_long_short_ratio": None,
            "fm_sum_toptrader_long_short_ratio": None,
            "fm_count_long_short_ratio": None,
            "fm_taker_long_short_vol_ratio": None,
            "fm_top_vs_global_ratio_spread": None,
            "fm_taker_vs_global_ratio_spread": None,
            "fm_global_vs_market_median_spread": None,
            "fm_top_vs_market_median_spread": None,
            "fm_ratio_missing_count": None,
        }

    current_time = _as_datetime(current["metrics_time"])
    median_values = metrics_index.market_medians_by_time.get(current_time, {})
    global_ratio = _optional_float(current["count_long_short_ratio"])
    top_ratio = _optional_float(current["sum_toptrader_long_short_ratio"])
    taker_ratio = _optional_float(current["sum_taker_long_short_vol_ratio"])
    return {
        **base,
        "fm_metrics_match": 1,
        "fm_metrics_age_minutes": (decision_time - current_time).total_seconds() / 60,
        "fm_sum_open_interest_value": _optional_float(current["sum_open_interest_value"]),
        "fm_oi_value_change_1h": _open_interest_change(symbol, decision_time, 60, metrics_index),
        "fm_oi_value_change_4h": _open_interest_change(symbol, decision_time, 240, metrics_index),
        "fm_count_toptrader_long_short_ratio": _optional_float(
            current["count_toptrader_long_short_ratio"]
        ),
        "fm_sum_toptrader_long_short_ratio": top_ratio,
        "fm_count_long_short_ratio": global_ratio,
        "fm_taker_long_short_vol_ratio": taker_ratio,
        "fm_top_vs_global_ratio_spread": _spread(top_ratio, global_ratio),
        "fm_taker_vs_global_ratio_spread": _spread(taker_ratio, global_ratio),
        "fm_global_vs_market_median_spread": _spread(
            global_ratio,
            median_values.get("count_long_short_ratio"),
        ),
        "fm_top_vs_market_median_spread": _spread(
            top_ratio,
            median_values.get("sum_toptrader_long_short_ratio"),
        ),
        "fm_ratio_missing_count": sum(1 for field in RATIO_COLUMNS if current[field] is None),
    }


def _categorical_feature_flags(symbol: str, decision_time: datetime) -> dict[str, int]:
    hour = decision_time.hour
    session_flags = {
        "fm_session_asia": int(0 <= hour < 8),
        "fm_session_europe": int(8 <= hour < 16),
        "fm_session_us": int(hour >= 16),
    }
    symbol_flags = {
        f"fm_symbol_{known_symbol.removesuffix('USDT').lower()}": int(symbol == known_symbol)
        for known_symbol in KNOWN_SYMBOLS
    }
    group_flags = {name: int(symbol in symbols) for name, symbols in SYMBOL_GROUPS.items()}
    return {**session_flags, **symbol_flags, **group_flags}


def _lookup_metric_row(
    symbol: str,
    decision_time: datetime,
    metrics_index: _MetricsIndex,
) -> dict[str, object] | None:
    times = metrics_index.times_by_symbol.get(symbol)
    if not times:
        return None
    index = bisect.bisect_right(times, decision_time) - 1
    if index < 0:
        return None
    metrics_time = times[index]
    if decision_time - metrics_time > metrics_index.max_age:
        return None
    return metrics_index.rows_by_symbol[symbol][index]


def _open_interest_change(
    symbol: str,
    decision_time: datetime,
    lag_minutes: int,
    metrics_index: _MetricsIndex,
) -> float | None:
    current = _lookup_metric_row(symbol, decision_time, metrics_index)
    lagged = _lookup_metric_row(
        symbol, decision_time - timedelta(minutes=lag_minutes), metrics_index
    )
    if current is None or lagged is None:
        return None
    current_value = _optional_float(current["sum_open_interest_value"])
    lagged_value = _optional_float(lagged["sum_open_interest_value"])
    if current_value is None or lagged_value is None or lagged_value <= 0:
        return None
    return (current_value / lagged_value) - 1


def _market_medians(rows: list[dict[str, object]]) -> dict[str, float]:
    medians: dict[str, float] = {}
    for field in RATIO_COLUMNS:
        values = [_optional_float(row[field]) for row in rows]
        non_null_values = [value for value in values if value is not None]
        if non_null_values:
            medians[field] = statistics.median(non_null_values)
    return medians


def _normalize_metric_row(row: dict[str, object]) -> dict[str, object]:
    normalized = dict(row)
    normalized["metrics_time"] = _as_datetime(normalized["metrics_time"])
    return normalized


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FuturesMetricsSelectedFeaturesError(f"missing JSON input: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FuturesMetricsSelectedFeaturesError(f"JSON input must be an object: {path}")
    return payload


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _spread(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_futures_metrics_selected_features(
        FuturesMetricsSelectedFeaturesConfig.from_path(args.config)
    )
    for window in payload["windows"]:
        window_item = dict(window)
        print(
            f"{window_item['name']}: rows={window_item['row_count']} "
            f"matched={window_item['matched_metrics_count']} "
            f"path={window_item['output_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
