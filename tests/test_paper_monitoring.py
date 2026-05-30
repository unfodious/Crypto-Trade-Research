import json
from pathlib import Path

import pytest

from crypto_trade_research.models.artifacts import (
    ExpectedRidgeArtifact,
    FeatureSchema,
    LinearProbabilityArtifact,
    ModelArtifact,
    write_model_artifact,
)
from crypto_trade_research.paper_monitoring import (
    PaperMonitoringConfig,
    build_paper_monitoring_report,
)


def test_build_paper_monitoring_report_marks_replay_as_not_forward_evidence(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, evidence_type="historical_replay_seed")

    payload = build_paper_monitoring_report(config)

    assert payload["schema_version"] == "research.paper-monitoring-report.v1"
    assert payload["metrics"]["trade_count"] == 3
    assert payload["metrics"]["average_r_after_costs"] > 0
    assert payload["model_artifact_status"]["expected_r_model_available"] is True
    assert payload["monitoring_status"] == "gate_failed"
    assert payload["decision"]["forward_paper_gate_passed"] is False
    assert "historical replay seed" in payload["warnings"][0]


def test_build_paper_monitoring_report_can_pass_forward_paper_gate(tmp_path: Path) -> None:
    config = _config(tmp_path, evidence_type="forward_paper")

    payload = build_paper_monitoring_report(config)

    assert all(gate["passed"] for gate in payload["gate_results"])
    assert payload["monitoring_status"] == "pass"
    assert payload["decision"]["forward_paper_gate_passed"] is True


def test_build_paper_monitoring_report_uses_trade_risk_for_computed_drawdown(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, evidence_type="forward_paper", include_source_metrics=False)

    payload = build_paper_monitoring_report(config)

    assert payload["metrics"]["max_drawdown_pct"] == pytest.approx(0.00125)


def _config(
    tmp_path: Path,
    *,
    evidence_type: str,
    include_source_metrics: bool = True,
) -> PaperMonitoringConfig:
    model_path = _write_model_artifact(tmp_path)
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "candidate_name": "unit_candidate",
                "source_artifacts": {"model_artifact": {"path": str(model_path)}},
                "paper_gate": {
                    "minimum_calendar_days": 1,
                    "minimum_paper_trades": 3,
                    "minimum_average_r_after_costs": 0.0,
                    "maximum_simulated_drawdown_pct": 0.08,
                    "maximum_single_day_positive_r_share": 1.0,
                    "minimum_positive_symbol_breadth": 0.5,
                    "minimum_positive_session_breadth": 0.5,
                },
            }
        ),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "trades": [
                    _trade("2026-05-27T01:00:00Z", "TONUSDT", 1.0),
                    _trade("2026-05-27T09:00:00Z", "ICPUSDT", 1.0),
                    _trade("2026-05-27T17:00:00Z", "TONUSDT", -0.5),
                ],
                "metrics": {"max_drawdown_pct": 0.01, "max_drawdown_duration": 1}
                if include_source_metrics
                else {},
            }
        ),
        encoding="utf-8",
    )
    return PaperMonitoringConfig.from_dict(
        {
            "report_name": "unit",
            "output_path": str(tmp_path / "report.json"),
            "issue_id": "CT-135",
            "epic_id": "CT-113",
            "pack_manifest_path": str(pack_path),
            "ledger_source_path": str(ledger_path),
            "ledger_strategy_name": "unit",
            "evidence_type": evidence_type,
        }
    )


def _trade(decision_time: str, symbol: str, net_r: float) -> dict[str, object]:
    return {
        "decision_time": decision_time,
        "symbol": symbol,
        "net_r": net_r,
        "paper_risk_per_trade_pct": 0.0025,
        "feature_freshness_seconds": 0,
        "funding_source_latency_seconds": 0,
    }


def _write_model_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "model_artifact.json"
    write_model_artifact(
        path,
        ModelArtifact(
            model_id="unit_candidate",
            model_version="20260527T000000Z",
            model=LinearProbabilityArtifact(
                feature_name="funding_rate",
                threshold=-0.00002,
                positive_direction=-1,
                probability_threshold=0.55,
            ),
            expected_r_model=ExpectedRidgeArtifact(
                feature_names=("funding_rate",),
                means={"funding_rate": 0.0},
                standard_deviations={"funding_rate": 0.001},
                intercept=0.0,
                weights={"funding_rate": -1.0},
                expected_r_threshold=-0.2,
            ),
            feature_schema=FeatureSchema(
                feature_set_version="features.unit.v1",
                feature_names=("funding_rate",),
            ),
            preprocessing={"missing_value_policy": "fail_closed"},
            calibration={"method": "unit"},
            dataset_manifest_path="data/generated/unit/manifest.json",
            training_data_hash="abc123",
            research_git_commit="abc123",
            dependency_versions={"python": "3.12"},
            created_at="2026-05-27T00:00:00Z",
        ),
    )
    return path
