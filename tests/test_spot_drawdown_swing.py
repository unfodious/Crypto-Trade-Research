import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.spot_drawdown_swing import (
    SpotDrawdownSwingConfig,
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
