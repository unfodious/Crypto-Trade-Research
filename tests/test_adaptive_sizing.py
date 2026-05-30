import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_trade_research.adaptive_sizing import (
    AdaptiveSizingConfig,
    build_adaptive_sizing_report,
)


def test_adaptive_sizing_uses_only_realized_exits_for_drawdown_throttle(
    tmp_path: Path,
) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            {
                "decision_time": "2026-01-01T00:00:00Z",
                "exit_time": "2026-01-01T02:00:00Z",
                "symbol": "SOLUSDT",
                "side": "long",
                "net_r": -10.0,
            },
            {
                "decision_time": "2026-01-01T01:00:00Z",
                "exit_time": "2026-01-01T03:00:00Z",
                "symbol": "SUIUSDT",
                "side": "long",
                "net_r": 1.0,
            },
            {
                "decision_time": "2026-01-01T02:30:00Z",
                "exit_time": "2026-01-01T04:00:00Z",
                "symbol": "AVAXUSDT",
                "side": "long",
                "net_r": 1.0,
            },
        ],
    )

    payload = build_adaptive_sizing_report(
        AdaptiveSizingConfig.from_dict(
            {
                "report_name": "unit_adaptive",
                "issue_id": "CT-183",
                "epic_id": "CT-113",
                "initial_equity": 1000,
                "max_drawdown_gate_pct": 0.08,
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [
                    {
                        "name": "throttle_after_realized_dd",
                        "base_risk_per_trade_pct": 0.01,
                        "drawdown_risk_steps": [
                            {"at_drawdown_pct": 0.05, "risk_per_trade_pct": 0.001}
                        ],
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["accepted_trade_count"] == 3
    assert scenario["final_equity"] == pytest.approx(910.9)
    assert scenario["average_risk_per_trade_pct"] == pytest.approx(0.007)
    assert scenario["max_drawdown_pct"] == pytest.approx(0.1)


def test_adaptive_sizing_applies_daily_signal_cap(tmp_path: Path) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            {
                "decision_time": "2026-01-01T00:00:00Z",
                "exit_time": "2026-01-01T00:10:00Z",
                "symbol": "SOLUSDT",
                "side": "long",
                "net_r": 1.0,
            },
            {
                "decision_time": "2026-01-01T00:01:00Z",
                "exit_time": "2026-01-01T00:11:00Z",
                "symbol": "SUIUSDT",
                "side": "long",
                "net_r": 1.0,
            },
            {
                "decision_time": "2026-01-02T00:00:00Z",
                "exit_time": "2026-01-02T00:10:00Z",
                "symbol": "AVAXUSDT",
                "side": "long",
                "net_r": 1.0,
            },
        ],
    )

    payload = build_adaptive_sizing_report(
        AdaptiveSizingConfig.from_dict(
            {
                "report_name": "unit_adaptive",
                "issue_id": "CT-183",
                "epic_id": "CT-113",
                "initial_equity": 1000,
                "max_drawdown_gate_pct": 0.08,
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [
                    {
                        "name": "one_per_day",
                        "base_risk_per_trade_pct": 0.01,
                        "max_trades_per_day": 1,
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["accepted_trade_count"] == 2
    assert scenario["skipped_trade_count"] == 1
    assert scenario["final_equity"] == pytest.approx(1020.1)
    assert scenario["windows"][0]["skipped_trade_count"] == 1


def test_adaptive_sizing_applies_symbol_allowlist(tmp_path: Path) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            {
                "decision_time": "2026-01-01T00:00:00Z",
                "exit_time": "2026-01-01T00:10:00Z",
                "symbol": "SOLUSDT",
                "side": "long",
                "net_r": 1.0,
            },
            {
                "decision_time": "2026-01-01T00:01:00Z",
                "exit_time": "2026-01-01T00:11:00Z",
                "symbol": "ICPUSDT",
                "side": "long",
                "net_r": 100.0,
            },
        ],
    )

    payload = build_adaptive_sizing_report(
        AdaptiveSizingConfig.from_dict(
            {
                "report_name": "unit_adaptive",
                "issue_id": "CT-183",
                "epic_id": "CT-113",
                "initial_equity": 1000,
                "max_drawdown_gate_pct": 0.08,
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [
                    {
                        "name": "sol_only",
                        "base_risk_per_trade_pct": 0.01,
                        "allowed_symbols": ["SOLUSDT"],
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["accepted_trade_count"] == 1
    assert scenario["skipped_trade_count"] == 1
    assert scenario["final_equity"] == pytest.approx(1010.0)
    assert scenario["symbols"][0]["name"] == "SOLUSDT"


def _write_replay(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    replay_dir = tmp_path / "replay"
    trades_path = replay_dir / "pack" / "accepted_trades.parquet"
    trades_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), trades_path)
    replay_report_path = replay_dir / "replay_report.json"
    replay_report_path.write_text(
        json.dumps({"replays": [{"accepted_trades_path": "pack/accepted_trades.parquet"}]}),
        encoding="utf-8",
    )
    return replay_report_path
