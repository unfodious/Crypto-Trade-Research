from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.external_rotation_screen import (
    ExternalRotationFilter,
    ExternalRotationRule,
    ExternalRotationScreenConfig,
    _filter_matches,
    _position_metrics,
    build_external_rotation_screen_report,
)


def test_external_rotation_filter_uses_point_in_time_metric_join(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.parquet"
    market_path = tmp_path / "market.parquet"
    manifest_path = tmp_path / "manifest.json"
    spot_config_path = tmp_path / "spot.json"

    pq.write_table(
        pa.Table.from_pylist(
            [
                _metric_row("SOLUSDT", datetime(2026, 1, 1, 14, 0, tzinfo=UTC), 100),
                _metric_row("SOLUSDT", datetime(2026, 1, 1, 15, 0, tzinfo=UTC), 130),
                _metric_row("SOLUSDT", datetime(2026, 1, 1, 16, 0, tzinfo=UTC), 90),
            ]
        ),
        metrics_path,
    )
    pq.write_table(
        pa.Table.from_pylist(
            _market_rows(
                "SOLUSDT",
                [
                    *[(f"2026-01-01T{hour:02d}:00:00Z", 100.0) for hour in range(14)],
                    ("2026-01-01T14:00:00Z", 90.0),
                    ("2026-01-01T15:00:00Z", 92.0),
                    ("2026-01-01T16:00:00Z", 96.0),
                    ("2026-01-01T17:00:00Z", 101.0),
                    ("2026-01-01T18:00:00Z", 102.0),
                    ("2026-01-01T19:00:00Z", 103.0),
                ],
            )
        ),
        market_path,
    )
    manifest_path.write_text(f'{{"cleaned_path": "{market_path}"}}', encoding="utf-8")
    spot_config_path.write_text(
        """
        {
          "report_name": "unit_spot",
          "issue_id": "CT-200",
          "epic_id": "CT-113",
          "output_json_path": "unused.json",
          "output_markdown_path": "unused.md",
          "round_trip_cost_pct": 0.0,
          "timeframe_minutes": 60,
          "symbols": ["SOLUSDT"],
          "windows": [{"name": "unit", "dataset_manifest_path": "__MANIFEST__"}],
          "scenarios": [{
            "name": "unit_portfolio",
            "description": "unit",
            "drawdown_lookback_hours": 15,
            "min_drawdown_pct": 0.05,
            "min_reclaim_return_pct": 0.01,
            "max_rsi": 100,
            "min_rsi_rebound": -100,
            "min_close_location": 0,
            "min_lower_wick_ratio": 0,
            "profit_target_pct": 0.03,
            "min_hold_hours": 1,
            "max_hold_hours": 12,
            "min_bounce_from_low_pct": 0.0,
            "min_hours_since_low": 0,
            "sell_only_profitable": true,
            "portfolio_cash_usd": 1000,
            "initial_buy_usd": 100,
            "dca_buy_usd": 0,
            "max_symbol_allocation_usd": 100,
            "max_open_positions": 1,
            "dca_drop_levels_pct": []
          }]
        }
        """.replace("__MANIFEST__", str(manifest_path)),
        encoding="utf-8",
    )

    report = build_external_rotation_screen_report(
        ExternalRotationScreenConfig.from_dict(
            {
                "report_name": "unit_external",
                "issue_id": "CT-200",
                "epic_id": "CT-113",
                "spot_config_path": str(spot_config_path),
                "scenario_names": ["unit_portfolio"],
                "metrics_path": str(metrics_path),
                "max_metrics_age_minutes": 10,
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "rules": [
                    {
                        "name": "metrics_matched_base",
                        "require_metrics_match": True,
                        "filter_groups": [],
                    },
                    {
                        "name": "skip_oi_spike",
                        "require_metrics_match": True,
                        "filter_groups": [
                            [
                                {
                                    "feature": "fm_oi_value_change_1h",
                                    "operator": ">",
                                    "value": 0.2,
                                }
                            ]
                        ],
                    },
                ],
            }
        )
    )

    scenario = report["scenarios"][0]
    base, skip = scenario["rules"]
    assert scenario["matched_metrics_count"] == 1
    assert base["kept_position_count"] == 1
    assert skip["skipped_position_count"] == 1
    assert skip["kept_position_count"] == 0
    assert (tmp_path / "out" / "report.md").exists()


def test_external_rotation_filter_and_metrics_helpers() -> None:
    assert _filter_matches(ExternalRotationFilter("feature", ">", 1), {"feature": 2})
    assert not _filter_matches(ExternalRotationFilter("feature", ">", 1), {"feature": None})
    assert _filter_matches(ExternalRotationFilter("feature", "==", "x"), {"feature": "x"})

    rule = ExternalRotationRule(
        name="skip",
        description="",
        require_metrics_match=True,
        filter_groups=((ExternalRotationFilter("feature", ">", 1),),),
    )
    assert rule.filter_groups[0][0].feature == "feature"

    metrics = _position_metrics(
        [
            {
                "net_return_pct": 0.1,
                "status": "closed",
                "cost_usd": 100,
                "exit_value_usd": 110,
                "max_adverse_pct": -0.02,
                "max_favorable_pct": 0.12,
                "window": "w1",
                "symbol": "SOLUSDT",
            },
            {
                "net_return_pct": -0.05,
                "status": "closed",
                "cost_usd": 100,
                "exit_value_usd": 95,
                "max_adverse_pct": -0.07,
                "max_favorable_pct": 0.01,
                "window": "w2",
                "symbol": "SUIUSDT",
            },
        ]
    )
    assert metrics["position_count"] == 2
    assert metrics["profit_factor"] == 2.0
    assert metrics["positive_window_breadth"] == 0.5


def _metric_row(symbol: str, metrics_time: datetime, oi_value: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "metrics_time": metrics_time,
        "sum_open_interest_value": oi_value,
        "count_toptrader_long_short_ratio": 1.0,
        "sum_toptrader_long_short_ratio": 1.0,
        "count_long_short_ratio": 1.0,
        "sum_taker_long_short_vol_ratio": 1.0,
    }


def _market_rows(symbol: str, closes: list[tuple[str, float]]) -> list[dict[str, object]]:
    rows = []
    for timestamp, close in closes:
        close_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        rows.append(
            {
                "symbol": symbol,
                "open_time": close_time,
                "close_time": close_time,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1000.0,
            }
        )
    return rows
