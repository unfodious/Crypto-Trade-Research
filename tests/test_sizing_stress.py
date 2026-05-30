import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_trade_research.sizing_stress import SizingStressConfig, build_sizing_stress_report


def test_build_sizing_stress_report_computes_fixed_risk_monthly_pnl(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    trades_path = replay_dir / "pack" / "accepted_trades.parquet"
    _write_table(
        trades_path,
        [
            {
                "decision_time": "2026-01-01T00:00:00Z",
                "symbol": "SOLUSDT",
                "net_r": 1.0,
            },
            {
                "decision_time": "2026-01-02T00:00:00Z",
                "symbol": "SUIUSDT",
                "net_r": -1.0,
            },
            {
                "decision_time": "2026-02-01T00:00:00Z",
                "symbol": "AVAXUSDT",
                "net_r": 2.0,
            },
        ],
    )
    replay_report_path = replay_dir / "replay_report.json"
    _write_json(
        replay_report_path,
        {"replays": [{"accepted_trades_path": "pack/accepted_trades.parquet"}]},
    )

    payload = build_sizing_stress_report(
        SizingStressConfig.from_dict(
            {
                "report_name": "unit_sizing",
                "issue_id": "CT-182",
                "epic_id": "CT-113",
                "initial_equity": 1000,
                "fixed_risk_per_trade_pcts": [0.01],
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["trade_count"] == 3
    assert scenario["final_equity"] == 1019.898
    assert scenario["max_drawdown_pct"] == pytest.approx(0.01)
    assert scenario["monthly"][0]["month"] == "2026-01"
    assert scenario["monthly"][0]["trade_count"] == 2
    assert scenario["monthly"][1]["month"] == "2026-02"
    assert (tmp_path / "out" / "report.json").exists()
    assert "Fixed Risk 1.00%" in (tmp_path / "out" / "report.md").read_text(encoding="utf-8")


def _write_table(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
