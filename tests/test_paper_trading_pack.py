import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_trade_research.models.artifacts import (
    FeatureSchema,
    LinearProbabilityArtifact,
    ModelArtifact,
    write_model_artifact,
)
from crypto_trade_research.paper_trading import (
    PaperTradingPackConfig,
    build_paper_trading_pack,
)


def test_build_paper_trading_pack_is_research_only(tmp_path: Path) -> None:
    config = _config(tmp_path)

    payload = build_paper_trading_pack(config)

    assert payload["schema_version"] == "research.paper-trading-pack.v1"
    assert payload["candidate"]["model_id"] == "unit_candidate"
    assert payload["candidate"]["feature_count"] == 1
    assert payload["research_evidence"]["oos_average_r"] == 0.25
    assert payload["research_evidence"]["stability_status"] == "pass"
    assert payload["safety"]["live_order_authority"] is False
    assert "place_live_order" in payload["safety"]["forbidden_actions"]
    assert payload["decision"]["paper_trading_approved"] is True
    assert payload["decision"]["live_trading_approved"] is False
    assert payload["decision"]["working_model"] is False
    assert config.output_path.exists()


def test_paper_trading_pack_rejects_live_authority_fields(tmp_path: Path) -> None:
    payload = _raw_config(tmp_path)
    payload["strategy"]["leverage"] = 5

    with pytest.raises(ValueError, match="forbidden live authority field"):
        PaperTradingPackConfig.from_dict(payload)


def _config(tmp_path: Path) -> PaperTradingPackConfig:
    return PaperTradingPackConfig.from_dict(_raw_config(tmp_path))


def _raw_config(tmp_path: Path) -> dict[str, object]:
    model_path = _write_model_artifact(tmp_path)
    baseline_path = tmp_path / "baseline_report.json"
    baseline_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "funding_manifest_path": "data/generated/funding/manifest.json",
                },
                "model_metadata": {
                    "primary_strategy": "expected_r_ridge_risk_controlled_oos",
                    "training_target": "target_before_stop",
                    "risk_controls": {"max_trades_per_decision_time": 3},
                },
                "strategies": {
                    "expected_r_ridge_risk_controlled_oos": {
                        "average_r": 0.25,
                        "trade_count": 120,
                        "max_drawdown_pct": 0.04,
                        "profit_factor": 1.5,
                    },
                    "rule_only_oos": {
                        "average_r": -0.4,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    stability_path = tmp_path / "stability_report.json"
    stability_path.write_text(
        json.dumps({"stability_report": {"status": "pass"}}),
        encoding="utf-8",
    )
    experiment_config_path = tmp_path / "experiment_config.json"
    experiment_config_path.write_text(json.dumps({"experiment_name": "unit_candidate"}))
    return {
        "pack_name": "unit_pack",
        "output_path": str(tmp_path / "pack_manifest.json"),
        "issue_id": "CT-132",
        "epic_id": "CT-113",
        "candidate_name": "unit_candidate",
        "plan_path": "docs/experiments/unit.md",
        "source_artifacts": {
            "model_artifact_path": str(model_path),
            "baseline_report_path": str(baseline_path),
            "stability_report_path": str(stability_path),
            "experiment_config_path": str(experiment_config_path),
        },
        "strategy": {
            "side": "long",
            "timeframe": "1m",
            "symbols": ["TONUSDT"],
            "filters": [{"feature": "funding_rate", "operator": "<=", "value": -0.00002}],
            "ranking": {"score": "expected_r_ridge", "top_n_per_decision_time": 3},
            "exits": {"stop_loss_pct": 0.004, "target_pct": 0.008, "horizon_bars": 12},
        },
        "paper_gate": {"minimum_calendar_days": 30, "minimum_paper_trades": 100},
        "monitoring": {"required_metrics": ["paper_average_r_after_costs"]},
        "reconciliation": {"signal_rules": ["closed_1m_candles_only"]},
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
            feature_schema=FeatureSchema(
                feature_set_version="features.unit.v1",
                feature_names=("funding_rate",),
            ),
            preprocessing={"imputation": "none"},
            calibration={"method": "unit", "probability_threshold": 0.55},
            dataset_manifest_path="data/generated/unit/manifest.json",
            training_data_hash="abc123",
            research_git_commit="abc123",
            dependency_versions={"python": "3.12"},
            created_at=datetime(2026, 5, 27, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        ),
    )
    return path
