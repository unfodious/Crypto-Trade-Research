import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.forward_filter_diagnostics import (
    DiagnosticStreamConfig,
    ForwardFilterDiagnosticsConfig,
    build_forward_filter_diagnostics,
)


def test_build_forward_filter_diagnostics_reports_independent_and_sequential_counts(
    tmp_path: Path,
) -> None:
    pack_path = tmp_path / "pack.json"
    features_path = tmp_path / "features.parquet"
    forward_run_path = tmp_path / "forward_run.json"
    _write_json(
        pack_path,
        {
            "strategy": {
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "filters": [
                    {"feature": "funding_rate", "operator": "<=", "value": -0.00002},
                    {"feature": "risk_on_score_20", "operator": ">=", "value": 0.35},
                ],
            }
        },
    )
    _write_table(
        features_path,
        [
            {
                "symbol": "BTCUSDT",
                "decision_time": "2026-05-27T14:00:00Z",
                "funding_rate": -0.00003,
                "risk_on_score_20": 0.5,
            },
            {
                "symbol": "ETHUSDT",
                "decision_time": "2026-05-27T14:00:00Z",
                "funding_rate": -0.00001,
                "risk_on_score_20": 0.9,
            },
            {
                "symbol": "DOGEUSDT",
                "decision_time": "2026-05-27T14:00:00Z",
                "funding_rate": -0.1,
                "risk_on_score_20": 1.0,
            },
        ],
    )
    _write_json(
        forward_run_path,
        {"collector_summary": {"decision_time": "2026-05-27T14:00:00Z", "candidate_count": 1}},
    )

    report = build_forward_filter_diagnostics(
        ForwardFilterDiagnosticsConfig(
            report_name="unit_filter_diagnostics",
            issue_id="CT-167",
            epic_id="CT-113",
            output_json_path=tmp_path / "filter_diagnostics.json",
            output_markdown_path=tmp_path / "filter_diagnostics.md",
            streams=(
                DiagnosticStreamConfig(
                    name="unit_stream",
                    issue_id="CT-146",
                    pack_manifest_path=pack_path,
                    features_path=features_path,
                    forward_run_path=forward_run_path,
                ),
            ),
        )
    )

    stream = report["streams"][0]
    assert stream["strategy_row_count"] == 2
    assert stream["final_candidate_count"] == 1
    assert report["summary"]["total_final_candidate_rows"] == 1
    first_filter = stream["filters"][0]
    second_filter = stream["filters"][1]
    assert first_filter["independent_pass_count"] == 1
    assert first_filter["sequential_before_count"] == 2
    assert first_filter["sequential_after_count"] == 1
    assert second_filter["independent_pass_count"] == 2
    assert second_filter["sequential_before_count"] == 1
    assert second_filter["sequential_after_count"] == 1
    assert (tmp_path / "filter_diagnostics.json").exists()
    assert "unit_stream" in (tmp_path / "filter_diagnostics.md").read_text(encoding="utf-8")


def test_build_forward_filter_diagnostics_counts_missing_features(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.json"
    features_path = tmp_path / "features.parquet"
    forward_run_path = tmp_path / "forward_run.json"
    _write_json(
        pack_path,
        {
            "strategy": {
                "symbols": ["BTCUSDT"],
                "filters": [{"feature": "funding_rate", "operator": "<=", "value": -0.00002}],
            }
        },
    )
    _write_table(features_path, [{"symbol": "BTCUSDT", "decision_time": "2026-05-27T14:00:00Z"}])
    _write_json(forward_run_path, {"collector_summary": {"decision_time": "2026-05-27T14:00:00Z"}})

    report = build_forward_filter_diagnostics(
        ForwardFilterDiagnosticsConfig(
            report_name="unit_filter_diagnostics",
            issue_id="CT-167",
            epic_id="CT-113",
            output_json_path=tmp_path / "filter_diagnostics.json",
            output_markdown_path=tmp_path / "filter_diagnostics.md",
            streams=(
                DiagnosticStreamConfig(
                    name="unit_stream",
                    issue_id="CT-146",
                    pack_manifest_path=pack_path,
                    features_path=features_path,
                    forward_run_path=forward_run_path,
                ),
            ),
        )
    )

    filter_report = report["streams"][0]["filters"][0]
    assert filter_report["independent_pass_count"] == 0
    assert filter_report["independent_missing_count"] == 1
    assert filter_report["sequential_after_count"] == 0


def _write_table(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
