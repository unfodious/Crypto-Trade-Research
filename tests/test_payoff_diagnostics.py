import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.payoff_diagnostics import (
    PayoffDiagnosticsConfig,
    build_payoff_diagnostics_report,
)


def test_payoff_diagnostics_reports_clean_runner_share(tmp_path: Path) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            _row("2026-01-01T00:00:00Z", "SOLUSDT", 4.0, -0.5, 1.5, 0.62),
            _row("2026-01-01T01:00:00Z", "SOLUSDT", 4.0, -1.2, 1.5, 0.62),
            _row("2026-01-02T00:00:00Z", "SUIUSDT", 2.0, -0.4, -1.0, 0.62),
        ],
    )

    payload = build_payoff_diagnostics_report(
        PayoffDiagnosticsConfig.from_dict(
            {
                "report_name": "unit_payoff",
                "issue_id": "CT-187",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "runner_thresholds_r": [1, 3],
                "target_runner_r": 3,
                "min_clean_runner_share": 0.3,
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [
                    {
                        "name": "sol",
                        "allowed_symbols": ["SOLUSDT"],
                        "max_trades_per_day": 10,
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["accepted_trade_count"] == 2
    assert scenario["thresholds"][1]["runner_count"] == 2
    assert scenario["thresholds"][1]["clean_runner_count"] == 1
    assert scenario["target_runner_clean_share"] == 0.5
    assert scenario["passes_runner_floor"] is True
    assert (tmp_path / "out" / "report.md").exists()


def test_payoff_diagnostics_applies_probability_filter_and_daily_cap(tmp_path: Path) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            _row("2026-01-01T00:00:00Z", "SOLUSDT", 4.0, -0.5, 1.5, 0.62),
            _row("2026-01-01T01:00:00Z", "SOLUSDT", 4.0, -0.5, 1.5, 0.62),
            _row("2026-01-02T00:00:00Z", "SOLUSDT", 4.0, -0.5, 1.5, 0.55),
        ],
    )

    payload = build_payoff_diagnostics_report(
        PayoffDiagnosticsConfig.from_dict(
            {
                "report_name": "unit_payoff",
                "issue_id": "CT-187",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "runner_thresholds_r": [3],
                "target_runner_r": 3,
                "min_clean_runner_share": 0.8,
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [
                    {
                        "name": "prob60_one_per_day",
                        "min_probability": 0.6,
                        "max_trades_per_day": 1,
                    }
                ],
            }
        )
    )

    scenario = payload["scenarios"][0]
    assert scenario["accepted_trade_count"] == 1
    assert scenario["passes_runner_floor"] is True


def _row(
    decision_time: str,
    symbol: str,
    mfe: float,
    mae: float,
    realized_r: float,
    probability: float,
) -> dict[str, object]:
    return {
        "decision_time": decision_time,
        "exit_time": decision_time,
        "symbol": symbol,
        "timeframe": "1m",
        "expected_r": 0.5,
        "target_before_stop_probability": probability,
        "rank": 1,
        "realized_r_after_costs": realized_r,
        "max_favorable_excursion_r": mfe,
        "max_adverse_excursion_r": mae,
    }


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
