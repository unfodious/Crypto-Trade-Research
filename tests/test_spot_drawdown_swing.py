import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.spot_drawdown_swing import (
    SpotDrawdownSwingConfig,
    SpotSwingScenario,
    _entry_can_reach_profit,
    _entry_rank_passes,
    _rotate_positions,
    build_spot_drawdown_swing_report,
)


def test_spot_drawdown_swing_enters_after_exhaustion_and_exits_on_profit_fade(
    tmp_path: Path,
) -> None:
    manifest_path = _write_dataset(tmp_path)
    payload = build_spot_drawdown_swing_report(
        SpotDrawdownSwingConfig.from_dict(
            {
                "report_name": "unit_spot_swing",
                "issue_id": "CT-193",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "round_trip_cost_pct": 0.002,
                "timeframe_minutes": 60,
                "symbols": ["SOLUSDT"],
                "windows": [{"name": "unit", "dataset_manifest_path": str(manifest_path)}],
                "scenarios": [
                    {
                        "name": "unit_reclaim",
                        "description": "unit",
                        "drawdown_lookback_hours": 24,
                        "min_drawdown_pct": 0.08,
                        "min_reclaim_return_pct": 0.001,
                        "max_rsi": 60,
                        "min_rsi_rebound": 0.1,
                        "min_close_location": 0.5,
                        "min_lower_wick_ratio": 0.05,
                        "profit_target_pct": 0.03,
                        "min_hold_hours": 1,
                        "max_hold_hours": 24,
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["trade_count"] >= 1
    assert scenario["average_net_return_pct"] > 0
    assert (tmp_path / "out" / "report.md").exists()


def test_spot_drawdown_swing_portfolio_dca_reports_cash_cap(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path)
    payload = build_spot_drawdown_swing_report(
        SpotDrawdownSwingConfig.from_dict(
            {
                "report_name": "unit_spot_swing",
                "issue_id": "CT-193",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "portfolio.json"),
                "output_markdown_path": str(tmp_path / "out" / "portfolio.md"),
                "round_trip_cost_pct": 0.002,
                "timeframe_minutes": 60,
                "symbols": ["SOLUSDT"],
                "windows": [{"name": "unit", "dataset_manifest_path": str(manifest_path)}],
                "scenarios": [
                    {
                        "name": "unit_portfolio",
                        "description": "unit",
                        "drawdown_lookback_hours": 24,
                        "min_drawdown_pct": 0.08,
                        "min_reclaim_return_pct": 0.001,
                        "max_rsi": 60,
                        "min_rsi_rebound": 0.1,
                        "min_close_location": 0.5,
                        "min_lower_wick_ratio": 0.0,
                        "profit_target_pct": 0.03,
                        "min_hold_hours": 1,
                        "max_hold_hours": 24,
                        "sell_only_profitable": True,
                        "portfolio_cash_usd": 250,
                        "initial_buy_usd": 100,
                        "dca_buy_usd": 100,
                        "max_symbol_allocation_usd": 200,
                        "dca_drop_levels_pct": [0.05],
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["portfolio_cash_usd"] == 250
    assert scenario["by_window"][0]["initial_cash_usd"] == 250
    assert "monthly_returns" in scenario["by_window"][0]
    assert "max_portfolio_drawdown_pct" in scenario["by_window"][0]
    assert scenario["trade_count"] >= 1


def test_spot_drawdown_swing_portfolio_accepts_market_guard_config(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path)
    payload = build_spot_drawdown_swing_report(
        SpotDrawdownSwingConfig.from_dict(
            {
                "report_name": "unit_spot_swing",
                "issue_id": "CT-193",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "market_guard.json"),
                "output_markdown_path": str(tmp_path / "out" / "market_guard.md"),
                "round_trip_cost_pct": 0.002,
                "timeframe_minutes": 60,
                "symbols": ["SOLUSDT"],
                "windows": [{"name": "unit", "dataset_manifest_path": str(manifest_path)}],
                "scenarios": [
                    {
                        "name": "unit_market_guard",
                        "description": "unit",
                        "drawdown_lookback_hours": 24,
                        "min_drawdown_pct": 0.08,
                        "min_reclaim_return_pct": 0.001,
                        "max_rsi": 60,
                        "min_rsi_rebound": 0.1,
                        "min_close_location": 0.5,
                        "min_lower_wick_ratio": 0.0,
                        "profit_target_pct": 0.03,
                        "min_hold_hours": 1,
                        "max_hold_hours": 24,
                        "sell_only_profitable": True,
                        "portfolio_cash_usd": 250,
                        "initial_buy_usd": 100,
                        "dca_buy_usd": 100,
                        "max_symbol_allocation_usd": 200,
                        "max_open_positions": 1,
                        "dca_drop_levels_pct": [0.05],
                        "market_guard_for_entries": True,
                        "market_guard_for_dca": True,
                        "market_guard_lookback_hours": 1,
                        "min_market_bounce_from_low_pct": 0.0,
                        "market_recent_lookback_hours": 1,
                        "min_market_recent_return_pct": -1.0,
                        "min_market_positive_symbol_ratio": 0.0,
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["trade_count"] >= 1
    assert "average_max_portfolio_drawdown_pct" in scenario
    assert scenario["by_window"][0]["initial_cash_usd"] == 250


def test_spot_drawdown_swing_bear_leg_guard_can_abstain(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path)
    payload = build_spot_drawdown_swing_report(
        SpotDrawdownSwingConfig.from_dict(
            {
                "report_name": "unit_spot_swing",
                "issue_id": "CT-193",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "bear_guard.json"),
                "output_markdown_path": str(tmp_path / "out" / "bear_guard.md"),
                "round_trip_cost_pct": 0.002,
                "timeframe_minutes": 60,
                "symbols": ["SOLUSDT"],
                "windows": [{"name": "unit", "dataset_manifest_path": str(manifest_path)}],
                "scenarios": [
                    {
                        "name": "unit_bear_guard",
                        "description": "unit",
                        "drawdown_lookback_hours": 24,
                        "min_drawdown_pct": 0.08,
                        "min_reclaim_return_pct": 0.001,
                        "max_rsi": 60,
                        "min_rsi_rebound": 0.1,
                        "min_close_location": 0.5,
                        "min_lower_wick_ratio": 0.0,
                        "profit_target_pct": 0.03,
                        "min_hold_hours": 1,
                        "max_hold_hours": 24,
                        "trend_lookback_hours": 24,
                        "min_trend_return_pct": 0.01,
                        "sell_only_profitable": True,
                        "portfolio_cash_usd": 250,
                        "initial_buy_usd": 100,
                        "dca_buy_usd": 100,
                        "max_symbol_allocation_usd": 200,
                        "dca_drop_levels_pct": [0.05],
                        "market_guard_for_entries": True,
                        "market_guard_for_dca": True,
                        "market_guard_lookback_hours": 1,
                        "min_market_bounce_from_low_pct": 0.0,
                        "market_recent_lookback_hours": 1,
                        "min_market_recent_return_pct": -1.0,
                        "min_market_positive_symbol_ratio": 0.0,
                        "market_trend_lookback_hours": 24,
                        "min_market_trend_return_pct": 0.01,
                    }
                ],
            }
        )
    )

    assert payload["scenarios"][0]["trade_count"] == 0


def test_spot_drawdown_swing_partial_take_profit_reports_partial_exit(
    tmp_path: Path,
) -> None:
    manifest_path = _write_dataset(tmp_path)
    payload = build_spot_drawdown_swing_report(
        SpotDrawdownSwingConfig.from_dict(
            {
                "report_name": "unit_spot_swing",
                "issue_id": "CT-193",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "partial.json"),
                "output_markdown_path": str(tmp_path / "out" / "partial.md"),
                "round_trip_cost_pct": 0.002,
                "timeframe_minutes": 60,
                "symbols": ["SOLUSDT"],
                "windows": [{"name": "unit", "dataset_manifest_path": str(manifest_path)}],
                "scenarios": [
                    {
                        "name": "unit_partial",
                        "description": "unit",
                        "drawdown_lookback_hours": 24,
                        "min_drawdown_pct": 0.08,
                        "min_reclaim_return_pct": 0.001,
                        "max_rsi": 60,
                        "min_rsi_rebound": 0.1,
                        "min_close_location": 0.5,
                        "min_lower_wick_ratio": 0.0,
                        "profit_target_pct": 0.05,
                        "partial_take_profit_pct": 0.02,
                        "partial_take_profit_fraction": 0.5,
                        "trailing_stop_from_peak_pct": 0.01,
                        "min_hold_hours": 1,
                        "max_hold_hours": 24,
                        "sell_only_profitable": True,
                        "portfolio_cash_usd": 250,
                        "initial_buy_usd": 100,
                        "dca_buy_usd": 100,
                        "max_symbol_allocation_usd": 200,
                        "dca_drop_levels_pct": [0.05],
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["partial_exit_count"] >= 1
    assert scenario["by_window"][0]["partial_exit_count"] >= 1


def test_spot_drawdown_swing_rotation_redeploys_profitable_weak_position() -> None:
    scenario = SpotDrawdownSwingConfig.from_dict(
        {
            "report_name": "unit_spot_swing",
            "issue_id": "CT-193",
            "epic_id": "CT-113",
            "output_json_path": "/tmp/unused.json",
            "output_markdown_path": "/tmp/unused.md",
            "round_trip_cost_pct": 0.002,
            "timeframe_minutes": 60,
            "symbols": ["SOLUSDT", "SUIUSDT"],
            "windows": [],
            "scenarios": [
                {
                    "name": "unit_rotation",
                    "description": "unit",
                    "drawdown_lookback_hours": 2,
                    "min_drawdown_pct": 0.08,
                    "min_reclaim_return_pct": 0.001,
                    "max_rsi": 60,
                    "min_rsi_rebound": 0.1,
                    "min_close_location": 0.5,
                    "min_lower_wick_ratio": 0.0,
                    "profit_target_pct": 0.10,
                    "min_hold_hours": 1,
                    "max_hold_hours": 24,
                    "portfolio_cash_usd": 250,
                    "initial_buy_usd": 50,
                    "dca_buy_usd": 50,
                    "max_symbol_allocation_usd": 100,
                    "dca_drop_levels_pct": [0.05],
                    "rotation_lookback_hours": 2,
                    "min_rotation_profit_pct": 0.02,
                    "min_rotation_exit_rank_pct": 0.5,
                    "max_rotation_entry_rank_pct": 0.5,
                }
            ],
        }
    ).scenarios[0]
    now = datetime(2026, 1, 1, 16, tzinfo=UTC)
    sol_padding = [
        _row("SOLUSDT", now - timedelta(hours=15 - index), 110, 110, 109, 110, index)
        for index in range(13)
    ]
    sui_padding = [
        _row("SUIUSDT", now - timedelta(hours=15 - index), 95, 96, 94, 95, index)
        for index in range(13)
    ]
    symbol_rows = {
        "SOLUSDT": sol_padding
        + [
            _row("SOLUSDT", now - timedelta(hours=2), 110, 110, 109, 110, 13),
            _row("SOLUSDT", now - timedelta(hours=1), 105, 106, 104, 105, 14),
            _row("SOLUSDT", now, 103, 105, 102, 104, 15),
        ],
        "SUIUSDT": sui_padding
        + [
            _row("SUIUSDT", now - timedelta(hours=2), 95, 110, 90, 95, 13),
            _row("SUIUSDT", now - timedelta(hours=1), 96, 100, 92, 96, 14),
            _row("SUIUSDT", now, 99, 103, 98, 101, 15),
        ],
    }
    current_rows = {symbol: rows[-1] for symbol, rows in symbol_rows.items()}
    positions = {
        "SOLUSDT": {
            "symbol": "SOLUSDT",
            "entry_time": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "qty": 1.0,
            "cost_usd": 100.0,
            "realized_cost_usd": 0.0,
            "realized_value_usd": 0.0,
            "lot_count": 1,
            "dca_count": 0,
            "partial_exit_count": 0,
            "max_adverse_pct": 0.0,
            "max_favorable_pct": 0.04,
        }
    }
    completed: list[dict[str, object]] = []

    cash = _rotate_positions(
        0.0,
        completed,
        positions,
        current_rows,
        symbol_rows,
        scenario,
        {},
        0.0,
    )

    assert cash == 54.0
    assert completed[0]["exit_reason"] == "rotation_redeploy"
    assert "SOLUSDT" not in positions
    assert "SUIUSDT" in positions


def test_spot_drawdown_swing_entry_rank_filter_requires_relative_strength() -> None:
    scenario = SpotDrawdownSwingConfig.from_dict(
        {
            "report_name": "unit_spot_swing",
            "issue_id": "CT-193",
            "epic_id": "CT-113",
            "output_json_path": "/tmp/unused.json",
            "output_markdown_path": "/tmp/unused.md",
            "round_trip_cost_pct": 0.002,
            "timeframe_minutes": 60,
            "symbols": ["SOLUSDT", "SUIUSDT"],
            "windows": [],
            "scenarios": [
                {
                    "name": "unit_entry_rank",
                    "description": "unit",
                    "drawdown_lookback_hours": 2,
                    "min_drawdown_pct": 0.08,
                    "min_reclaim_return_pct": 0.001,
                    "max_rsi": 60,
                    "min_rsi_rebound": 0.1,
                    "min_close_location": 0.5,
                    "min_lower_wick_ratio": 0.0,
                    "profit_target_pct": 0.10,
                    "min_hold_hours": 1,
                    "max_hold_hours": 24,
                    "entry_rank_lookback_hours": 2,
                    "max_entry_rank_pct": 0.5,
                    "min_entry_rank_return_pct": 0.01,
                }
            ],
        }
    ).scenarios[0]
    now = datetime(2026, 1, 1, 16, tzinfo=UTC)
    symbol_rows = {
        "SOLUSDT": [
            _row("SOLUSDT", now - timedelta(hours=2), 100, 101, 99, 100, 0),
            _row("SOLUSDT", now - timedelta(hours=1), 103, 104, 102, 103, 1),
            _row("SOLUSDT", now, 108, 109, 107, 108, 2),
        ],
        "SUIUSDT": [
            _row("SUIUSDT", now - timedelta(hours=2), 100, 101, 99, 100, 0),
            _row("SUIUSDT", now - timedelta(hours=1), 99, 100, 98, 99, 1),
            _row("SUIUSDT", now, 98, 99, 97, 98, 2),
        ],
    }
    current_rows = {symbol: rows[-1] for symbol, rows in symbol_rows.items()}

    assert _entry_rank_passes("SOLUSDT", current_rows, symbol_rows, scenario)
    assert not _entry_rank_passes("SUIUSDT", current_rows, symbol_rows, scenario)


def test_spot_drawdown_swing_entry_profit_lookahead_filter() -> None:
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    rows = [
        _row("SOLUSDT", now - timedelta(hours=5), 100, 101, 99, 100, 0),
        _row("SOLUSDT", now - timedelta(hours=4), 100, 100, 97, 98, 1),
        _row("SOLUSDT", now - timedelta(hours=3), 98, 99, 96, 97, 2),
        _row("SOLUSDT", now - timedelta(hours=2), 97, 98, 94, 95, 3),
        _row("SOLUSDT", now - timedelta(hours=1), 95, 96, 93, 94, 4),
        _row("SOLUSDT", now - timedelta(hours=0), 94, 95, 92, 93, 5),
    ]
    config = SpotDrawdownSwingConfig.from_dict(
        {
            "report_name": "unit_spot_swing",
            "issue_id": "CT-193",
            "epic_id": "CT-113",
            "output_json_path": "/tmp/unused.json",
            "output_markdown_path": "/tmp/unused.md",
            "round_trip_cost_pct": 0.002,
            "timeframe_minutes": 60,
            "symbols": ["SOLUSDT"],
            "windows": [],
            "scenarios": [
                {
                    "name": "unit_lookahead",
                    "description": "unit",
                    "drawdown_lookback_hours": 1,
                    "min_drawdown_pct": 0.01,
                    "min_reclaim_return_pct": -1.0,
                    "max_rsi": 100,
                    "min_rsi_rebound": -100,
                    "min_close_location": 0.0,
                    "min_lower_wick_ratio": 0.0,
                    "profit_target_pct": 0.05,
                    "min_hold_hours": 1,
                    "max_hold_hours": 24,
                    "entry_profit_lookahead_hours": 2,
                }
            ],
        }
    )
    scenario = config.scenarios[0]
    assert not _entry_can_reach_profit(
        scenario=scenario,
        rows=rows,
        row=rows[0],
        config=config,
    )
    optimistic_rows = [dict(row) for row in rows]
    optimistic_rows[2]["high"] = 111.0
    optimistic_scenario = SpotSwingScenario.from_dict(
        {
            "name": "unit_lookahead",
            "description": "unit",
            "drawdown_lookback_hours": 1,
            "min_drawdown_pct": 0.01,
            "min_reclaim_return_pct": -1.0,
            "max_rsi": 100,
            "min_rsi_rebound": -100,
            "min_close_location": 0.0,
            "min_lower_wick_ratio": 0.0,
            "profit_target_pct": 0.05,
            "min_hold_hours": 1,
            "max_hold_hours": 24,
            "entry_profit_lookahead_hours": 5,
        }
    )
    assert _entry_can_reach_profit(
        config=config,
        scenario=optimistic_scenario,
        rows=optimistic_rows,
        row=rows[0],
    )


def _write_dataset(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "dataset"
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    price = 100.0
    for hour in range(60):
        close_time = start + timedelta(hours=hour + 1)
        if hour < 24:
            price = 100.0
        elif hour < 40:
            price -= 0.8
        elif hour == 40:
            price += 1.0
        elif hour < 45:
            price += 1.2
        else:
            price -= 0.2
        open_price = price - 0.2
        low = min(open_price, price) - (1.0 if hour == 40 else 0.1)
        high = max(open_price, price) + 0.2
        rows.append(
            {
                "symbol": "SOLUSDT",
                "open_time": close_time - timedelta(hours=1),
                "close_time": close_time,
                "open": open_price,
                "high": high,
                "low": low,
                "close": price,
                "volume": 1000.0,
            }
        )
    clean_path = dataset_dir / "clean" / "market_candles.parquet"
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), clean_path)
    manifest_path = dataset_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"cleaned_path": str(clean_path)}), encoding="utf-8")
    return manifest_path


def _row(
    symbol: str,
    close_time: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
    index: int,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "open_time": close_time - timedelta(hours=1),
        "close_time": close_time,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000.0,
        "_index": index,
        "return_1h_pct": 0.01,
        "rsi_14": 40.0,
        "rsi_delta": 1.0,
        "close_location": 0.8,
        "lower_wick_ratio": 0.1,
        "ema_9": close - 1,
    }
