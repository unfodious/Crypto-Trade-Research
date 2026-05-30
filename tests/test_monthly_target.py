import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_trade_research.monthly_target import (
    MonthlyTargetConfig,
    build_monthly_target_report,
)


def test_monthly_target_report_replays_filtered_signals_and_daily_cap(tmp_path: Path) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            {
                "decision_time": "2026-01-01T00:00:00Z",
                "exit_time": "2026-01-01T00:10:00Z",
                "symbol": "SOLUSDT",
                "timeframe": "1m",
                "expected_r": 0.2,
                "target_before_stop_probability": 0.61,
                "rank": 1,
                "realized_r_after_costs": 2.0,
            },
            {
                "decision_time": "2026-01-01T01:00:00Z",
                "exit_time": "2026-01-01T01:10:00Z",
                "symbol": "SOLUSDT",
                "timeframe": "1m",
                "expected_r": 0.2,
                "target_before_stop_probability": 0.61,
                "rank": 1,
                "realized_r_after_costs": 2.0,
            },
            {
                "decision_time": "2026-02-01T00:00:00Z",
                "exit_time": "2026-02-01T00:10:00Z",
                "symbol": "SUIUSDT",
                "timeframe": "1m",
                "expected_r": 0.01,
                "target_before_stop_probability": 0.56,
                "rank": 1,
                "realized_r_after_costs": 100.0,
            },
        ],
    )

    payload = build_monthly_target_report(
        MonthlyTargetConfig.from_dict(
            {
                "report_name": "unit_monthly_target",
                "issue_id": "CT-186",
                "epic_id": "CT-113",
                "initial_equity": 1000,
                "target_monthly_return_pct": 0.03,
                "max_drawdown_gate_pct": 0.08,
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [
                    {
                        "name": "sol_one_per_day",
                        "risk_per_trade_pct": 0.01,
                        "max_trades_per_day": 1,
                        "allowed_symbols": ["SOLUSDT"],
                        "min_probability": 0.60,
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["accepted_trade_count"] == 1
    assert scenario["skipped_trade_count"] == 1
    assert scenario["final_equity"] == pytest.approx(1020.0)
    assert scenario["geometric_average_monthly_return_pct"] == pytest.approx(0.02)
    assert scenario["passes_monthly_target"] is False
    assert (tmp_path / "out" / "report.md").exists()


def test_monthly_target_report_marks_monthly_target_viable_only_with_drawdown_gate(
    tmp_path: Path,
) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            {
                "decision_time": "2026-01-01T00:00:00Z",
                "exit_time": "2026-01-01T00:10:00Z",
                "symbol": "SOLUSDT",
                "timeframe": "1m",
                "expected_r": 0.5,
                "target_before_stop_probability": 0.70,
                "rank": 1,
                "realized_r_after_costs": 10.0,
            },
            {
                "decision_time": "2026-02-01T00:00:00Z",
                "exit_time": "2026-02-01T00:10:00Z",
                "symbol": "SOLUSDT",
                "timeframe": "1m",
                "expected_r": 0.5,
                "target_before_stop_probability": 0.70,
                "rank": 1,
                "realized_r_after_costs": -10.0,
            },
        ],
    )

    payload = build_monthly_target_report(
        MonthlyTargetConfig.from_dict(
            {
                "report_name": "unit_monthly_target",
                "issue_id": "CT-186",
                "epic_id": "CT-113",
                "initial_equity": 1000,
                "target_monthly_return_pct": 0.20,
                "max_drawdown_gate_pct": 0.08,
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [{"name": "too_hot", "risk_per_trade_pct": 0.05}],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["best_month"]["return_pct"] == pytest.approx(0.5)
    assert scenario["max_drawdown_pct"] == pytest.approx(0.5)
    assert scenario["passes_drawdown_gate"] is False
    assert payload["decision"]["working_model"] is False


def _write_replay(tmp_path: Path, selected_rows: list[dict[str, object]]) -> Path:
    replay_dir = tmp_path / "replay"
    selected_path = replay_dir / "pack" / "selected_trades.parquet"
    pack_manifest_path = tmp_path / "pack_manifest.json"
    _write_table(selected_path, selected_rows)
    _write_json(
        pack_manifest_path,
        {
            "strategy": {
                "risk_controls": {
                    "max_trades_per_decision_time": 3,
                    "max_trades_per_symbol": 600,
                    "loss_cooldown_signals": 0,
                }
            }
        },
    )
    replay_report_path = replay_dir / "replay_report.json"
    _write_json(
        replay_report_path,
        {
            "replays": [
                {
                    "pack_manifest_path": str(pack_manifest_path),
                    "trades_path": "pack/selected_trades.parquet",
                }
            ]
        },
    )
    return replay_report_path


def _write_table(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
