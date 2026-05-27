import json
from pathlib import Path

from crypto_trade_research.evidence_readiness import (
    EvidenceReadinessConfig,
    ForwardPaperStreamConfig,
    build_evidence_readiness_report,
)


def test_build_evidence_readiness_report_blocks_sparse_forward_evidence(tmp_path: Path) -> None:
    external_path = _write_external_run(tmp_path, row_count=572)
    stream = _write_stream(
        tmp_path,
        name="ct145",
        cumulative_signals=0,
        closed_trades=0,
        calendar_days=0,
    )

    report = build_evidence_readiness_report(
        _config(tmp_path, external_path=external_path, streams=(stream,))
    )

    assert report["schema_version"] == "research.ct113_forward_evidence_readiness.v1"
    assert report["readiness_status"] == "not_ready"
    assert report["decision"]["ready_for_external_validation_matrix"] is False
    assert report["decision"]["working_model"] is False
    assert report["decision"]["live_trading_approved"] is False
    gates = {gate["name"]: gate for gate in report["gates"]}
    assert gates["external_feature_rows"]["passed"] is True
    assert gates["minimum_forward_signals"]["passed"] is False
    assert gates["minimum_closed_trades"]["passed"] is False
    assert (tmp_path / "readiness.json").exists()
    assert "Readiness status: `not_ready`" in (tmp_path / "readiness.md").read_text(
        encoding="utf-8"
    )


def test_build_evidence_readiness_report_passes_when_forward_evidence_is_sufficient(
    tmp_path: Path,
) -> None:
    external_path = _write_external_run(tmp_path, row_count=1000)
    stream = _write_stream(
        tmp_path,
        name="ct145",
        cumulative_signals=40,
        closed_trades=31,
        calendar_days=8,
    )

    report = build_evidence_readiness_report(
        _config(tmp_path, external_path=external_path, streams=(stream,))
    )

    assert report["readiness_status"] == "ready_for_validation"
    assert report["decision"]["ready_for_external_validation_matrix"] is True
    assert all(gate["passed"] for gate in report["gates"])


def _config(
    tmp_path: Path,
    *,
    external_path: Path,
    streams: tuple[ForwardPaperStreamConfig, ...],
) -> EvidenceReadinessConfig:
    return EvidenceReadinessConfig(
        report_name="unit_readiness",
        issue_id="CT-164",
        epic_id="CT-113",
        output_json_path=tmp_path / "readiness.json",
        output_markdown_path=tmp_path / "readiness.md",
        external_features_run_path=external_path,
        forward_paper_streams=streams,
        minimum_external_feature_rows=500,
        minimum_crowding_snapshots=1,
        minimum_order_book_snapshots=1,
        minimum_liquidation_snapshots=1,
        minimum_forward_signals=30,
        minimum_closed_trades=30,
        minimum_calendar_days=7,
    )


def _write_external_run(tmp_path: Path, *, row_count: int) -> Path:
    path = tmp_path / "external_forward_features_run.json"
    _write_json(
        path,
        {
            "latest_generated_at": "2026-05-27T14:22:07Z",
            "row_count": row_count,
            "crowding_snapshot_count": 42,
            "order_book_snapshot_count": 7,
            "liquidation_snapshot_count": 3,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "warnings": [],
        },
    )
    return path


def _write_stream(
    tmp_path: Path,
    *,
    name: str,
    cumulative_signals: int,
    closed_trades: int,
    calendar_days: int,
) -> ForwardPaperStreamConfig:
    stream_dir = tmp_path / name
    forward_run_path = stream_dir / "forward_run.json"
    monitoring_path = stream_dir / "monitoring_report.json"
    _write_json(
        forward_run_path,
        {
            "collector_summary": {
                "decision_time": "2026-05-27T14:00:00Z",
                "candidate_count": 1,
                "signal_count": 1 if cumulative_signals else 0,
                "take_count": 1 if closed_trades else 0,
            },
            "row_counts": {
                "cumulative_signals": cumulative_signals,
                "cumulative_trades": closed_trades,
                "closed_trades": closed_trades,
                "open_trades": 0,
            },
        },
    )
    _write_json(
        monitoring_path,
        {
            "monitoring_status": "gate_failed",
            "metrics": {
                "calendar_days": calendar_days,
                "trade_count": closed_trades,
                "average_r_after_costs": 0.1,
                "max_drawdown_pct": 0.01,
            },
            "warnings": [],
            "decision": {"working_model": False, "live_trading_approved": False},
        },
    )
    return ForwardPaperStreamConfig(
        name=name,
        issue_id="CT-146",
        forward_run_path=forward_run_path,
        monitoring_report_path=monitoring_path,
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
