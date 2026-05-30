"""Spot-style drawdown exhaustion swing scan."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

SCHEMA_VERSION = "research.spot-drawdown-swing.v1"


@dataclass(frozen=True, slots=True)
class SpotSwingWindow:
    name: str
    dataset_manifest_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SpotSwingWindow:
        return cls(
            name=str(payload["name"]),
            dataset_manifest_path=Path(str(payload["dataset_manifest_path"])),
        )


@dataclass(frozen=True, slots=True)
class SpotSwingScenario:
    name: str
    description: str
    drawdown_lookback_hours: int
    min_drawdown_pct: float
    min_reclaim_return_pct: float
    max_rsi: float
    min_rsi_rebound: float
    min_close_location: float
    min_lower_wick_ratio: float
    profit_target_pct: float
    max_hold_hours: int
    min_hold_hours: int = 1
    trend_lookback_hours: int | None = None
    min_trend_return_pct: float | None = None
    min_bounce_from_low_pct: float = 0.0
    min_hours_since_low: int = 0
    require_close_above_ema: bool = False
    recent_lookback_hours: int | None = None
    min_recent_return_pct: float | None = None
    min_positive_closes: int = 0
    sell_only_profitable: bool = False
    portfolio_cash_usd: float | None = None
    initial_buy_usd: float | None = None
    dca_buy_usd: float | None = None
    max_symbol_allocation_usd: float | None = None
    dca_drop_levels_pct: tuple[float, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SpotSwingScenario:
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            drawdown_lookback_hours=int(payload["drawdown_lookback_hours"]),
            min_drawdown_pct=float(payload["min_drawdown_pct"]),
            min_reclaim_return_pct=float(payload.get("min_reclaim_return_pct", 0.0)),
            max_rsi=float(payload.get("max_rsi", 100.0)),
            min_rsi_rebound=float(payload.get("min_rsi_rebound", -100.0)),
            min_close_location=float(payload.get("min_close_location", 0.0)),
            min_lower_wick_ratio=float(payload.get("min_lower_wick_ratio", 0.0)),
            profit_target_pct=float(payload["profit_target_pct"]),
            max_hold_hours=int(payload["max_hold_hours"]),
            min_hold_hours=int(payload.get("min_hold_hours", 1)),
            trend_lookback_hours=_optional_int(payload.get("trend_lookback_hours")),
            min_trend_return_pct=_optional_float(payload.get("min_trend_return_pct")),
            min_bounce_from_low_pct=float(payload.get("min_bounce_from_low_pct", 0.0)),
            min_hours_since_low=int(payload.get("min_hours_since_low", 0)),
            require_close_above_ema=bool(payload.get("require_close_above_ema", False)),
            recent_lookback_hours=_optional_int(payload.get("recent_lookback_hours")),
            min_recent_return_pct=_optional_float(payload.get("min_recent_return_pct")),
            min_positive_closes=int(payload.get("min_positive_closes", 0)),
            sell_only_profitable=bool(payload.get("sell_only_profitable", False)),
            portfolio_cash_usd=_optional_float(payload.get("portfolio_cash_usd")),
            initial_buy_usd=_optional_float(payload.get("initial_buy_usd")),
            dca_buy_usd=_optional_float(payload.get("dca_buy_usd")),
            max_symbol_allocation_usd=_optional_float(payload.get("max_symbol_allocation_usd")),
            dca_drop_levels_pct=tuple(
                float(item) for item in payload.get("dca_drop_levels_pct", [])
            ),
        )


@dataclass(frozen=True, slots=True)
class SpotDrawdownSwingConfig:
    report_name: str
    issue_id: str
    epic_id: str
    output_json_path: Path
    output_markdown_path: Path
    symbols: tuple[str, ...]
    round_trip_cost_pct: float
    timeframe_minutes: int
    windows: tuple[SpotSwingWindow, ...]
    scenarios: tuple[SpotSwingScenario, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SpotDrawdownSwingConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            symbols=tuple(str(item) for item in payload["symbols"]),
            round_trip_cost_pct=float(payload.get("round_trip_cost_pct", 0.002)),
            timeframe_minutes=int(payload.get("timeframe_minutes", 60)),
            windows=tuple(SpotSwingWindow.from_dict(dict(item)) for item in payload["windows"]),
            scenarios=tuple(
                SpotSwingScenario.from_dict(dict(item)) for item in payload["scenarios"]
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> SpotDrawdownSwingConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_spot_drawdown_swing_report(config: SpotDrawdownSwingConfig) -> dict[str, object]:
    """Run the spot-style drawdown exhaustion scan and write report artifacts."""

    if not config.symbols:
        raise ValueError("symbols must not be empty")
    if config.timeframe_minutes <= 0:
        raise ValueError("timeframe_minutes must be positive")
    if not config.scenarios:
        raise ValueError("scenarios must not be empty")

    window_bars = {
        window.name: _load_window_bars(window, config.symbols, config.timeframe_minutes)
        for window in config.windows
    }
    scenarios = [_scenario_report(config, scenario, window_bars) for scenario in config.scenarios]
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "market_data_note": (
            "Initial screen uses existing USD-M futures OHLCV as a price-action proxy. "
            "A true spot candidate requires spot OHLCV and spot fee validation."
        ),
        "round_trip_cost_pct": config.round_trip_cost_pct,
        "timeframe_minutes": config.timeframe_minutes,
        "symbols": list(config.symbols),
        "windows": [
            {"name": window.name, "dataset_manifest_path": str(window.dataset_manifest_path)}
            for window in config.windows
        ],
        "scenarios": scenarios,
        "buy_and_hold": _buy_and_hold_report(window_bars, config.round_trip_cost_pct),
        "decision": _decision(scenarios),
    }
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _load_window_bars(
    window: SpotSwingWindow,
    symbols: tuple[str, ...],
    timeframe_minutes: int,
) -> dict[str, list[dict[str, object]]]:
    manifest = json.loads(window.dataset_manifest_path.read_text(encoding="utf-8"))
    cleaned_path = Path(str(manifest["cleaned_path"]))
    fast_rows = _try_load_aggregated_bars_with_polars(cleaned_path, symbols, timeframe_minutes)
    if fast_rows is not None:
        return {symbol: _with_indicators(rows) for symbol, rows in fast_rows.items() if rows}

    table = pq.read_table(
        cleaned_path,
        columns=["symbol", "open_time", "close_time", "open", "high", "low", "close", "volume"],
    ).to_pydict()
    by_symbol: dict[str, list[dict[str, object]]] = {symbol: [] for symbol in symbols}
    symbol_set = set(symbols)
    for index, symbol_value in enumerate(table["symbol"]):
        symbol = str(symbol_value)
        if symbol not in symbol_set:
            continue
        by_symbol[symbol].append(
            {
                "symbol": symbol,
                "open_time": table["open_time"][index],
                "close_time": table["close_time"][index],
                "open": table["open"][index],
                "high": table["high"][index],
                "low": table["low"][index],
                "close": table["close"][index],
                "volume": table["volume"][index],
            }
        )
    return {
        symbol: _with_indicators(_aggregate_bars(symbol_rows, timeframe_minutes))
        for symbol, symbol_rows in by_symbol.items()
        if symbol_rows
    }


def _try_load_aggregated_bars_with_polars(
    cleaned_path: Path,
    symbols: tuple[str, ...],
    timeframe_minutes: int,
) -> dict[str, list[dict[str, object]]] | None:
    try:
        import polars as pl  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return None

    frame_seconds = timeframe_minutes * 60
    rows = (
        pl.scan_parquet(str(cleaned_path))
        .filter(pl.col("symbol").is_in(list(symbols)))
        .select(["symbol", "open_time", "close_time", "open", "high", "low", "close", "volume"])
        .with_columns(
            (
                (((pl.col("close_time").dt.epoch("s") - 1) // frame_seconds) + 1) * frame_seconds
            ).alias("bucket_epoch")
        )
        .sort(["symbol", "close_time"])
        .group_by(["symbol", "bucket_epoch"], maintain_order=True)
        .agg(
            [
                pl.col("open_time").first().alias("open_time"),
                pl.col("close_time").last().alias("close_time"),
                pl.col("open").first().alias("open"),
                pl.col("high").max().alias("high"),
                pl.col("low").min().alias("low"),
                pl.col("close").last().alias("close"),
                pl.col("volume").sum().alias("volume"),
            ]
        )
        .sort(["symbol", "close_time"])
        .collect()
        .to_dicts()
    )
    by_symbol: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    return by_symbol


def _aggregate_bars(
    rows: list[dict[str, object]], timeframe_minutes: int
) -> list[dict[str, object]]:
    rows = sorted(rows, key=lambda row: _as_datetime(row["close_time"]))
    output: list[dict[str, object]] = []
    current: list[dict[str, object]] = []
    for row in rows:
        current.append(row)
        close_time = _as_datetime(row["close_time"])
        if _total_minutes(close_time) % timeframe_minutes != 0:
            continue
        first = current[0]
        last = current[-1]
        output.append(
            {
                "symbol": first["symbol"],
                "open_time": first["open_time"],
                "close_time": last["close_time"],
                "open": _as_float(first["open"]),
                "high": max(_as_float(item["high"]) for item in current),
                "low": min(_as_float(item["low"]) for item in current),
                "close": _as_float(last["close"]),
                "volume": sum(_as_float(item["volume"]) for item in current),
            }
        )
        current = []
    return output


def _with_indicators(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    gains: list[float] = []
    losses: list[float] = []
    for index, row in enumerate(rows):
        previous_close = _as_float(rows[index - 1]["close"]) if index else _as_float(row["close"])
        close = _as_float(row["close"])
        change = close - previous_close
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
        row["return_1h_pct"] = _return(close, previous_close)
        row["rsi_14"] = _rsi(gains, losses, index, 14)
        previous_rsi = rows[index - 1].get("rsi_14") if index else None
        row["rsi_delta"] = (
            _as_float(row["rsi_14"]) - _as_float(previous_rsi)
            if row.get("rsi_14") is not None and previous_rsi is not None
            else None
        )
        bar_range = max(_as_float(row["high"]) - _as_float(row["low"]), 0.0)
        row["close_location"] = (
            (_as_float(row["close"]) - _as_float(row["low"])) / bar_range if bar_range else 0.5
        )
        row["lower_wick_ratio"] = (
            (min(_as_float(row["open"]), close) - _as_float(row["low"])) / bar_range
            if bar_range
            else 0.0
        )
        row["upper_wick_ratio"] = (
            (_as_float(row["high"]) - max(_as_float(row["open"]), close)) / bar_range
            if bar_range
            else 0.0
        )
        row["ema_9"] = _ema(rows, index, 9)
    return rows


def _scenario_report(
    config: SpotDrawdownSwingConfig,
    scenario: SpotSwingScenario,
    window_bars: dict[str, dict[str, list[dict[str, object]]]],
) -> dict[str, object]:
    if scenario.portfolio_cash_usd is not None:
        return _portfolio_scenario_report(config, scenario, window_bars)

    trades: list[dict[str, object]] = []
    for window_name, symbol_rows in window_bars.items():
        for symbol, rows in symbol_rows.items():
            trades.extend(_scenario_trades(config, scenario, window_name, symbol, rows))
    by_window = _group_metrics(trades, "window")
    by_symbol = _group_metrics(trades, "symbol")
    return {
        "name": scenario.name,
        "description": scenario.description,
        "trade_count": len(trades),
        **_trade_metrics(trades),
        "by_window": by_window,
        "by_symbol": by_symbol,
        "passes_initial_gate": _passes_initial_gate(trades, by_window, by_symbol),
    }


def _portfolio_scenario_report(
    config: SpotDrawdownSwingConfig,
    scenario: SpotSwingScenario,
    window_bars: dict[str, dict[str, list[dict[str, object]]]],
) -> dict[str, object]:
    reports = [
        _portfolio_window_report(config, scenario, window_name, symbol_rows)
        for window_name, symbol_rows in window_bars.items()
    ]
    positions = [
        position
        for report in reports
        for position in report["positions"]  # type: ignore[index]
    ]
    by_symbol = _group_metrics([dict(position) for position in positions], "symbol")
    closed = [dict(position) for position in positions if position.get("status") == "closed"]
    open_positions = [dict(position) for position in positions if position.get("status") == "open"]
    return {
        "name": scenario.name,
        "description": scenario.description,
        "trade_count": len(positions),
        "closed_trade_count": len(closed),
        "open_trade_count": len(open_positions),
        "average_net_return_pct": _mean(
            [_as_float(report["portfolio_return_pct"]) for report in reports]
        ),
        "average_closed_net_return_pct": _mean(
            [_as_float(position["net_return_pct"]) for position in closed]
        ),
        "average_open_unrealized_pct": _mean(
            [_as_float(position["net_return_pct"]) for position in open_positions]
        ),
        "median_net_return_pct": _median(
            [_as_float(report["portfolio_return_pct"]) for report in reports]
        ),
        "win_rate": (
            sum(_as_float(position["net_return_pct"]) > 0 for position in closed) / len(closed)
            if closed
            else 0.0
        ),
        "profit_factor": _profit_factor(
            [_as_float(position["net_return_pct"]) for position in closed]
        ),
        "average_holding_hours": _mean(
            [_as_float(position["holding_hours"]) for position in positions]
        ),
        "average_max_adverse_pct": _mean(
            [_as_float(position["max_adverse_pct"]) for position in positions]
        ),
        "portfolio_cash_usd": scenario.portfolio_cash_usd,
        "by_window": [
            {key: value for key, value in report.items() if key != "positions"}
            for report in reports
        ],
        "by_symbol": by_symbol,
        "passes_initial_gate": _portfolio_passes_initial_gate(reports, positions),
    }


def _portfolio_window_report(
    config: SpotDrawdownSwingConfig,
    scenario: SpotSwingScenario,
    window_name: str,
    symbol_rows: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    initial_cash = float(scenario.portfolio_cash_usd or 0.0)
    fee_rate = config.round_trip_cost_pct / 2
    cash = initial_cash
    positions: dict[str, dict[str, object]] = {}
    completed: list[dict[str, object]] = []
    rows_by_time = _rows_by_time(symbol_rows)

    for decision_time in sorted(rows_by_time):
        for symbol, row in rows_by_time[decision_time]:
            position = positions.get(symbol)
            if position is None:
                if _portfolio_entry_passes(scenario, symbol_rows[symbol], row):
                    spend = _buy_size(cash, scenario.initial_buy_usd, None, scenario)
                    if spend > 0:
                        positions[symbol] = _new_position(symbol, row, spend, fee_rate)
                        cash -= spend
                continue

            _update_position_excursions(position, row, fee_rate)
            if _should_dca(position, row, scenario) and _portfolio_dca_passes(scenario, row):
                spend = _buy_size(cash, scenario.dca_buy_usd, position, scenario)
                if spend > 0:
                    _add_lot(position, row, spend, fee_rate)
                    cash -= spend

            if _position_net_return(
                position, row, fee_rate
            ) >= scenario.profit_target_pct and _rebound_is_fading_in_row(symbol_rows[symbol], row):
                cash += _position_value(position, row, fee_rate)
                completed.append(_close_position(position, row, fee_rate, "profit_fade"))
                del positions[symbol]

    open_positions = [
        _close_position(position, symbol_rows[symbol][-1], fee_rate, "open_unrealized")
        for symbol, position in sorted(positions.items())
    ]
    for position in open_positions:
        position["status"] = "open"
    for position in completed + open_positions:
        position["window"] = window_name
    final_equity = cash + sum(
        _position_value(
            positions[str(position["symbol"])],
            symbol_rows[str(position["symbol"])][-1],
            fee_rate,
        )
        for position in open_positions
    )
    all_positions = completed + open_positions
    closed_returns = [_as_float(position["net_return_pct"]) for position in completed]
    open_returns = [_as_float(position["net_return_pct"]) for position in open_positions]
    return {
        "name": window_name,
        "initial_cash_usd": initial_cash,
        "final_equity_usd": final_equity,
        "cash_usd": cash,
        "invested_market_value_usd": final_equity - cash,
        "portfolio_return_pct": _return(final_equity, initial_cash),
        "closed_trade_count": len(completed),
        "open_trade_count": len(open_positions),
        "average_net_return_pct": _return(final_equity, initial_cash),
        "average_closed_net_return_pct": _mean(closed_returns),
        "average_open_unrealized_pct": _mean(open_returns),
        "median_net_return_pct": _median(closed_returns + open_returns),
        "win_rate": (
            sum(value > 0 for value in closed_returns) / len(closed_returns)
            if closed_returns
            else 0.0
        ),
        "profit_factor": _profit_factor(closed_returns),
        "positions": all_positions,
    }


def _rows_by_time(
    symbol_rows: dict[str, list[dict[str, object]]],
) -> dict[datetime, list[tuple[str, dict[str, object]]]]:
    rows_by_time: dict[datetime, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    for symbol, rows in symbol_rows.items():
        for row in rows:
            rows_by_time[_as_datetime(row["close_time"])].append((symbol, row))
    return rows_by_time


def _portfolio_entry_passes(
    scenario: SpotSwingScenario,
    rows: list[dict[str, object]],
    row: dict[str, object],
) -> bool:
    index = rows.index(row)
    if index < max(scenario.drawdown_lookback_hours, 15):
        return False
    lookback_rows = rows[index - scenario.drawdown_lookback_hours : index + 1]
    rolling_high = max(_as_float(item["high"]) for item in lookback_rows)
    rolling_low = min(_as_float(item["low"]) for item in lookback_rows)
    return _entry_passes(
        row,
        scenario,
        _return(_as_float(row["close"]), rolling_high),
        _trend_return(rows, index, scenario),
        _return(_as_float(row["close"]), rolling_low),
        _hours_since_low(lookback_rows),
        _recent_return(rows, index, scenario),
        _positive_close_count(rows, index, scenario.min_positive_closes),
    )


def _portfolio_dca_passes(scenario: SpotSwingScenario, row: dict[str, object]) -> bool:
    if _as_float(row["return_1h_pct"]) < scenario.min_reclaim_return_pct:
        return False
    ema_9 = row.get("ema_9")
    return not (
        scenario.require_close_above_ema
        and (ema_9 is None or _as_float(row["close"]) <= _as_float(ema_9))
    )


def _buy_size(
    cash: float,
    requested: float | None,
    position: dict[str, object] | None,
    scenario: SpotSwingScenario,
) -> float:
    if requested is None or cash <= 0:
        return 0.0
    cap_remaining = math.inf
    if scenario.max_symbol_allocation_usd is not None and position is not None:
        cap_remaining = scenario.max_symbol_allocation_usd - _as_float(position["cost_usd"])
    elif scenario.max_symbol_allocation_usd is not None:
        cap_remaining = scenario.max_symbol_allocation_usd
    return max(min(requested, cash, cap_remaining), 0.0)


def _new_position(
    symbol: str,
    row: dict[str, object],
    spend: float,
    fee_rate: float,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "entry_time": _format_timestamp(_as_datetime(row["close_time"])),
        "qty": spend * (1 - fee_rate) / _as_float(row["close"]),
        "cost_usd": spend,
        "lot_count": 1,
        "dca_count": 0,
        "max_adverse_pct": 0.0,
        "max_favorable_pct": 0.0,
    }


def _add_lot(
    position: dict[str, object],
    row: dict[str, object],
    spend: float,
    fee_rate: float,
) -> None:
    position["qty"] = _as_float(position["qty"]) + spend * (1 - fee_rate) / _as_float(row["close"])
    position["cost_usd"] = _as_float(position["cost_usd"]) + spend
    position["lot_count"] = int(position["lot_count"]) + 1
    position["dca_count"] = int(position["dca_count"]) + 1


def _should_dca(
    position: dict[str, object],
    row: dict[str, object],
    scenario: SpotSwingScenario,
) -> bool:
    dca_index = int(position["dca_count"])
    if dca_index >= len(scenario.dca_drop_levels_pct):
        return False
    return _position_net_return(position, row, 0.0) <= -abs(scenario.dca_drop_levels_pct[dca_index])


def _update_position_excursions(
    position: dict[str, object],
    row: dict[str, object],
    fee_rate: float,
) -> None:
    high_return = _position_return_at_price(position, _as_float(row["high"]), fee_rate)
    low_return = _position_return_at_price(position, _as_float(row["low"]), fee_rate)
    position["max_favorable_pct"] = max(_as_float(position["max_favorable_pct"]), high_return)
    position["max_adverse_pct"] = min(_as_float(position["max_adverse_pct"]), low_return)


def _position_value(
    position: dict[str, object],
    row: dict[str, object],
    fee_rate: float,
) -> float:
    return _as_float(position["qty"]) * _as_float(row["close"]) * (1 - fee_rate)


def _position_return_at_price(
    position: dict[str, object],
    price: float,
    fee_rate: float,
) -> float:
    return _return(
        _as_float(position["qty"]) * price * (1 - fee_rate), _as_float(position["cost_usd"])
    )


def _position_net_return(
    position: dict[str, object],
    row: dict[str, object],
    fee_rate: float,
) -> float:
    return _return(_position_value(position, row, fee_rate), _as_float(position["cost_usd"]))


def _close_position(
    position: dict[str, object],
    row: dict[str, object],
    fee_rate: float,
    reason: str,
) -> dict[str, object]:
    return {
        "window": "",
        "symbol": position["symbol"],
        "entry_time": position["entry_time"],
        "exit_time": _format_timestamp(_as_datetime(row["close_time"])),
        "holding_hours": (
            _as_datetime(row["close_time"]) - _as_datetime(position["entry_time"])
        ).total_seconds()
        / 3600,
        "lot_count": position["lot_count"],
        "cost_usd": position["cost_usd"],
        "exit_value_usd": _position_value(position, row, fee_rate),
        "net_return_pct": _position_net_return(position, row, fee_rate),
        "max_favorable_pct": position["max_favorable_pct"],
        "max_adverse_pct": position["max_adverse_pct"],
        "status": "closed",
        "exit_reason": reason,
    }


def _rebound_is_fading_in_row(rows: list[dict[str, object]], row: dict[str, object]) -> bool:
    index = rows.index(row)
    if index <= 0:
        return False
    return _rebound_is_fading(rows, index)


def _portfolio_passes_initial_gate(
    reports: list[dict[str, object]],
    positions: list[object],
) -> bool:
    return (
        bool(positions)
        and all(_as_float(report["portfolio_return_pct"]) > 0 for report in reports)
        and sum(int(report["open_trade_count"]) for report in reports) == 0
    )


def _scenario_trades(
    config: SpotDrawdownSwingConfig,
    scenario: SpotSwingScenario,
    window_name: str,
    symbol: str,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    trades: list[dict[str, object]] = []
    index = max(scenario.drawdown_lookback_hours, 15)
    while index < len(rows) - scenario.min_hold_hours - 1:
        row = rows[index]
        lookback_rows = rows[index - scenario.drawdown_lookback_hours : index + 1]
        rolling_high = max(_as_float(item["high"]) for item in lookback_rows)
        rolling_low = min(_as_float(item["low"]) for item in lookback_rows)
        drawdown = _return(_as_float(row["close"]), rolling_high)
        bounce_from_low = _return(_as_float(row["close"]), rolling_low)
        hours_since_low = _hours_since_low(lookback_rows)
        trend_return = _trend_return(rows, index, scenario)
        recent_return = _recent_return(rows, index, scenario)
        positive_closes = _positive_close_count(rows, index, scenario.min_positive_closes)
        if not _entry_passes(
            row,
            scenario,
            drawdown,
            trend_return,
            bounce_from_low,
            hours_since_low,
            recent_return,
            positive_closes,
        ):
            index += 1
            continue
        trade, exit_index = _exit_trade(config, scenario, window_name, symbol, rows, index)
        trades.append(trade)
        index = exit_index + 1
    return trades


def _entry_passes(
    row: dict[str, object],
    scenario: SpotSwingScenario,
    drawdown: float,
    trend_return: float | None,
    bounce_from_low: float,
    hours_since_low: int,
    recent_return: float | None,
    positive_closes: int,
) -> bool:
    rsi = row.get("rsi_14")
    rsi_delta = row.get("rsi_delta")
    if rsi is None or rsi_delta is None:
        return False
    if scenario.min_trend_return_pct is not None and (
        trend_return is None or trend_return < scenario.min_trend_return_pct
    ):
        return False
    if scenario.min_recent_return_pct is not None and (
        recent_return is None or recent_return < scenario.min_recent_return_pct
    ):
        return False
    ema_9 = row.get("ema_9")
    if scenario.require_close_above_ema and (
        ema_9 is None or _as_float(row["close"]) <= _as_float(ema_9)
    ):
        return False
    return (
        drawdown <= -abs(scenario.min_drawdown_pct)
        and bounce_from_low >= scenario.min_bounce_from_low_pct
        and hours_since_low >= scenario.min_hours_since_low
        and positive_closes >= scenario.min_positive_closes
        and _as_float(row["return_1h_pct"]) >= scenario.min_reclaim_return_pct
        and _as_float(rsi) <= scenario.max_rsi
        and _as_float(rsi_delta) >= scenario.min_rsi_rebound
        and _as_float(row["close_location"]) >= scenario.min_close_location
        and _as_float(row["lower_wick_ratio"]) >= scenario.min_lower_wick_ratio
    )


def _hours_since_low(rows: list[dict[str, object]]) -> int:
    lows = [_as_float(row["low"]) for row in rows]
    minimum = min(lows)
    last_low_index = max(index for index, value in enumerate(lows) if value == minimum)
    return len(rows) - 1 - last_low_index


def _recent_return(
    rows: list[dict[str, object]],
    index: int,
    scenario: SpotSwingScenario,
) -> float | None:
    if scenario.recent_lookback_hours is None:
        return None
    if index < scenario.recent_lookback_hours:
        return None
    return _return(
        _as_float(rows[index]["close"]),
        _as_float(rows[index - scenario.recent_lookback_hours]["close"]),
    )


def _positive_close_count(rows: list[dict[str, object]], index: int, lookback: int) -> int:
    if lookback <= 0 or index < lookback:
        return 0
    count = 0
    for current_index in range(index - lookback + 1, index + 1):
        if _as_float(rows[current_index]["close"]) > _as_float(rows[current_index - 1]["close"]):
            count += 1
    return count


def _trend_return(
    rows: list[dict[str, object]],
    index: int,
    scenario: SpotSwingScenario,
) -> float | None:
    if scenario.trend_lookback_hours is None:
        return None
    if index < scenario.trend_lookback_hours:
        return None
    return _return(
        _as_float(rows[index]["close"]),
        _as_float(rows[index - scenario.trend_lookback_hours]["close"]),
    )


def _exit_trade(
    config: SpotDrawdownSwingConfig,
    scenario: SpotSwingScenario,
    window_name: str,
    symbol: str,
    rows: list[dict[str, object]],
    entry_index: int,
) -> tuple[dict[str, object], int]:
    entry = rows[entry_index]
    entry_price = _as_float(entry["close"])
    exit_index = min(len(rows) - 1, entry_index + scenario.max_hold_hours)
    max_drawdown = 0.0
    max_favorable = 0.0
    exit_reason = "time_stop"
    status = "closed"
    last_possible_index = len(rows) - 1 if scenario.sell_only_profitable else exit_index
    for index in range(entry_index + 1, last_possible_index + 1):
        current = rows[index]
        raw_return = _return(_as_float(current["close"]), entry_price)
        max_favorable = max(max_favorable, _return(_as_float(current["high"]), entry_price))
        max_drawdown = min(max_drawdown, _return(_as_float(current["low"]), entry_price))
        if index - entry_index < scenario.min_hold_hours:
            continue
        if raw_return >= scenario.profit_target_pct and _rebound_is_fading(rows, index):
            exit_index = index
            exit_reason = "profit_fade"
            break
        if (
            scenario.sell_only_profitable
            and index >= entry_index + scenario.max_hold_hours
            and raw_return >= config.round_trip_cost_pct
            and _rebound_is_fading(rows, index)
        ):
            exit_index = index
            exit_reason = "profitable_time_fade"
            break
    else:
        if scenario.sell_only_profitable:
            exit_index = len(rows) - 1
            exit_reason = "open_unrealized"
            status = "open"
    exit_row = rows[exit_index]
    gross_return = _return(_as_float(exit_row["close"]), entry_price)
    net_return = gross_return - config.round_trip_cost_pct
    return (
        {
            "window": window_name,
            "symbol": symbol,
            "entry_time": _format_timestamp(_as_datetime(entry["close_time"])),
            "exit_time": _format_timestamp(_as_datetime(exit_row["close_time"])),
            "holding_hours": exit_index - entry_index,
            "entry_price": entry_price,
            "exit_price": _as_float(exit_row["close"]),
            "gross_return_pct": gross_return,
            "net_return_pct": net_return,
            "max_favorable_pct": max_favorable,
            "max_adverse_pct": max_drawdown,
            "status": status,
            "exit_reason": exit_reason,
        },
        exit_index,
    )


def _rebound_is_fading(rows: list[dict[str, object]], index: int) -> bool:
    row = rows[index]
    previous = rows[index - 1]
    close = _as_float(row["close"])
    return (
        close < _as_float(previous["close"])
        or (
            row.get("rsi_14") is not None
            and previous.get("rsi_14") is not None
            and _as_float(row["rsi_14"]) < _as_float(previous["rsi_14"])
        )
        or _as_float(row["upper_wick_ratio"]) >= 0.35
        or (row.get("ema_9") is not None and close < _as_float(row["ema_9"]))
    )


def _buy_and_hold_report(
    window_bars: dict[str, dict[str, list[dict[str, object]]]],
    round_trip_cost_pct: float,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for window_name, symbols in window_bars.items():
        returns = []
        for symbol, bars in symbols.items():
            if len(bars) < 2:
                continue
            net_return = (
                _return(_as_float(bars[-1]["close"]), _as_float(bars[0]["close"]))
                - round_trip_cost_pct
            )
            returns.append(net_return)
            rows.append({"window": window_name, "symbol": symbol, "net_return_pct": net_return})
        rows.append(
            {
                "window": window_name,
                "symbol": "equal_weight",
                "net_return_pct": _mean(returns) if returns else 0.0,
            }
        )
    return {
        "rows": rows,
        "average_equal_weight_return_pct": _mean(
            [_as_float(row["net_return_pct"]) for row in rows if row["symbol"] == "equal_weight"]
        ),
    }


def _group_metrics(trades: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade[key])].append(trade)
    return [{"name": name, **_trade_metrics(rows)} for name, rows in sorted(grouped.items())]


def _trade_metrics(trades: list[dict[str, object]]) -> dict[str, object]:
    returns = [_as_float(trade["net_return_pct"]) for trade in trades]
    closed = [trade for trade in trades if trade.get("status", "closed") == "closed"]
    open_trades = [trade for trade in trades if trade.get("status") == "open"]
    wins = [value for value in returns if value > 0]
    return {
        "closed_trade_count": len(closed),
        "open_trade_count": len(open_trades),
        "average_net_return_pct": _mean(returns),
        "average_closed_net_return_pct": _mean(
            [_as_float(trade["net_return_pct"]) for trade in closed]
        ),
        "average_open_unrealized_pct": _mean(
            [_as_float(trade["net_return_pct"]) for trade in open_trades]
        ),
        "median_net_return_pct": _median(returns),
        "win_rate": len(wins) / len(returns) if returns else 0.0,
        "profit_factor": _profit_factor(returns),
        "average_holding_hours": _mean([_as_float(trade["holding_hours"]) for trade in trades]),
        "average_max_adverse_pct": _mean([_as_float(trade["max_adverse_pct"]) for trade in trades]),
    }


def _profit_factor(returns: list[float]) -> float:
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    return sum(wins) / abs(sum(losses)) if losses else (math.inf if wins else 0.0)


def _passes_initial_gate(
    trades: list[dict[str, object]],
    by_window: list[dict[str, object]],
    by_symbol: list[dict[str, object]],
) -> bool:
    return (
        len(trades) >= 100
        and _trade_metrics(trades)["open_trade_count"] == 0
        and _trade_metrics(trades)["average_net_return_pct"] > 0
        and all(_as_float(row["average_net_return_pct"]) > 0 for row in by_window)
        and sum(_as_float(row["average_net_return_pct"]) > 0 for row in by_symbol)
        / max(len(by_symbol), 1)
        >= 0.6
    )


def _decision(scenarios: list[dict[str, object]]) -> dict[str, object]:
    passed = [scenario["name"] for scenario in scenarios if scenario["passes_initial_gate"]]
    return {
        "promote_to_paper": False,
        "working_model": False,
        "live_trading_approved": False,
        "initial_screen_passed": bool(passed),
        "passed_scenarios": passed,
        "notes": (
            "Research-only screen. A passing row would still require spot OHLCV validation "
            "and paper trading."
        ),
    }


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        f"Issue: `{payload['issue_id']}`",
        "",
        f"Market data note: {payload['market_data_note']}",
        "",
        "## Scenarios",
        "",
        (
            "| Scenario | Trades | Closed | Open | Avg MTM | Avg closed | Open unreal. | "
            "Win rate | PF | Gate |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for scenario in payload["scenarios"]:
        item = dict(scenario)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["name"]),
                    str(item["trade_count"]),
                    str(item["closed_trade_count"]),
                    str(item["open_trade_count"]),
                    _pct(item["average_net_return_pct"]),
                    _pct(item["average_closed_net_return_pct"]),
                    _pct(item["average_open_unrealized_pct"]),
                    _pct(item["win_rate"]),
                    _number(item["profit_factor"]),
                    "pass" if item["passes_initial_gate"] else "fail",
                ]
            )
            + " |"
        )
    lines.extend(
        ["", "## Decision", "", f"```json\n{json.dumps(payload['decision'], indent=2)}\n```", ""]
    )
    return "\n".join(lines)


def _rsi(gains: list[float], losses: list[float], index: int, window: int) -> float | None:
    if index < window:
        return None
    avg_gain = sum(gains[index - window + 1 : index + 1]) / window
    avg_loss = sum(losses[index - window + 1 : index + 1]) / window
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def _ema(rows: list[dict[str, object]], index: int, window: int) -> float | None:
    if index < window - 1:
        return None
    alpha = 2 / (window + 1)
    start = index - window + 1
    value = _mean([_as_float(row["close"]) for row in rows[start : index + 1]])
    for row in rows[start + 1 : index + 1]:
        value = alpha * _as_float(row["close"]) + (1 - alpha) * value
    return value


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _return(value: float, basis: float) -> float:
    return (value / basis) - 1 if basis else 0.0


def _total_minutes(value: datetime) -> int:
    return int(value.timestamp() // 60)


def _as_float(value: object) -> float:
    return float(value)  # type: ignore[arg-type]


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)  # type: ignore[arg-type]


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _pct(value: object) -> str:
    return f"{_as_float(value) * 100:.2f}%"


def _number(value: object) -> str:
    number = _as_float(value)
    if math.isinf(number):
        return "inf"
    return f"{number:.4f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    build_spot_drawdown_swing_report(SpotDrawdownSwingConfig.from_path(args.config))


if __name__ == "__main__":
    main()
