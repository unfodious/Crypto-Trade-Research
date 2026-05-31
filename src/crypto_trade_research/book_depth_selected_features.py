"""Join Binance book-depth features to selected-trade decision timestamps."""

from __future__ import annotations

import argparse
import bisect
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

KEY_COLUMNS = ("symbol", "timeframe", "decision_time")
FEATURE_COLUMNS = (
    "symbol",
    "depth_time",
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
)
JOINED_FEATURE_COLUMNS = (
    "bd_match",
    "bd_age_minutes",
    *FEATURE_COLUMNS[2:],
)


class BookDepthSelectedFeaturesError(ValueError):
    """Raised when selected-trade book-depth features cannot be built."""


@dataclass(frozen=True, slots=True)
class BookDepthSelectedWindowConfig:
    name: str
    selected_trades_path: Path
    output_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BookDepthSelectedWindowConfig:
        return cls(
            name=str(payload["name"]),
            selected_trades_path=Path(str(payload["selected_trades_path"])),
            output_path=Path(str(payload["output_path"])),
        )


@dataclass(frozen=True, slots=True)
class BookDepthSelectedFeaturesConfig:
    book_depth_features_path: Path
    max_depth_age_minutes: int
    windows: tuple[BookDepthSelectedWindowConfig, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BookDepthSelectedFeaturesConfig:
        return cls(
            book_depth_features_path=Path(str(payload["book_depth_features_path"])),
            max_depth_age_minutes=int(payload.get("max_depth_age_minutes", 5)),
            windows=tuple(
                BookDepthSelectedWindowConfig.from_dict(dict(item)) for item in payload["windows"]
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> BookDepthSelectedFeaturesConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class _BookDepthIndex:
    rows_by_symbol: dict[str, list[dict[str, object]]]
    times_by_symbol: dict[str, list[datetime]]
    max_age: timedelta


def build_book_depth_selected_features(
    config: BookDepthSelectedFeaturesConfig,
) -> dict[str, object]:
    """Build selected-trade feature rows using point-in-time book-depth lookup."""

    if config.max_depth_age_minutes <= 0:
        raise BookDepthSelectedFeaturesError("max_depth_age_minutes must be positive")
    book_depth_index = _load_book_depth_index(
        config.book_depth_features_path,
        config.max_depth_age_minutes,
    )
    windows = []
    for window in config.windows:
        keys = _selected_trade_keys(window.selected_trades_path)
        rows = [_feature_row(key, book_depth_index) for key in keys]
        window.output_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), window.output_path)
        windows.append(
            {
                "name": window.name,
                "selected_trades_path": str(window.selected_trades_path),
                "output_path": str(window.output_path),
                "row_count": len(rows),
                "matched_book_depth_count": sum(1 for row in rows if row["bd_match"] == 1),
            }
        )
    return {
        "book_depth_features_path": str(config.book_depth_features_path),
        "max_depth_age_minutes": config.max_depth_age_minutes,
        "windows": windows,
    }


def _load_book_depth_index(
    book_depth_features_path: Path,
    max_depth_age_minutes: int,
) -> _BookDepthIndex:
    if not book_depth_features_path.exists():
        raise BookDepthSelectedFeaturesError(
            f"missing book-depth features parquet: {book_depth_features_path}"
        )
    rows = [
        _normalize_feature_row(row)
        for row in pq.read_table(
            book_depth_features_path,
            columns=list(FEATURE_COLUMNS),
        ).to_pylist()
    ]
    rows_by_symbol: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        rows_by_symbol.setdefault(str(row["symbol"]), []).append(row)
    times_by_symbol: dict[str, list[datetime]] = {}
    for symbol, symbol_rows in rows_by_symbol.items():
        symbol_rows.sort(key=lambda item: _as_datetime(item["depth_time"]))
        times_by_symbol[symbol] = [_as_datetime(row["depth_time"]) for row in symbol_rows]
    return _BookDepthIndex(
        rows_by_symbol=rows_by_symbol,
        times_by_symbol=times_by_symbol,
        max_age=timedelta(minutes=max_depth_age_minutes),
    )


def _selected_trade_keys(selected_trades_path: Path) -> list[dict[str, object]]:
    if not selected_trades_path.exists():
        raise BookDepthSelectedFeaturesError(
            f"missing selected trades parquet: {selected_trades_path}"
        )
    keys: dict[tuple[object, ...], dict[str, object]] = {}
    for row in pq.read_table(selected_trades_path, columns=list(KEY_COLUMNS)).to_pylist():
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


def _feature_row(key: dict[str, object], book_depth_index: _BookDepthIndex) -> dict[str, object]:
    symbol = str(key["symbol"])
    decision_time = _as_datetime(key["decision_time"])
    current = _lookup_book_depth_row(symbol, decision_time, book_depth_index)
    base = {
        "symbol": symbol,
        "timeframe": str(key["timeframe"]),
        "decision_time": decision_time,
    }
    if current is None:
        return {
            **base,
            **{column: None for column in JOINED_FEATURE_COLUMNS},
            "bd_match": 0,
        }
    depth_time = _as_datetime(current["depth_time"])
    return {
        **base,
        "bd_match": 1,
        "bd_age_minutes": (decision_time - depth_time).total_seconds() / 60,
        **{column: current[column] for column in FEATURE_COLUMNS[2:]},
    }


def _lookup_book_depth_row(
    symbol: str,
    decision_time: datetime,
    book_depth_index: _BookDepthIndex,
) -> dict[str, object] | None:
    times = book_depth_index.times_by_symbol.get(symbol)
    if not times:
        return None
    index = bisect.bisect_right(times, decision_time) - 1
    if index < 0:
        return None
    depth_time = times[index]
    if decision_time - depth_time > book_depth_index.max_age:
        return None
    return book_depth_index.rows_by_symbol[symbol][index]


def _normalize_feature_row(row: dict[str, object]) -> dict[str, object]:
    normalized = dict(row)
    normalized["depth_time"] = _as_datetime(normalized["depth_time"])
    normalized["symbol"] = str(normalized["symbol"])
    return normalized


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError(f"expected datetime-compatible value, got {type(value)!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--summary-path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_cli_args()
    summary = build_book_depth_selected_features(
        BookDepthSelectedFeaturesConfig.from_path(args.config)
    )
    if args.summary_path:
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(args.summary_path)
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
