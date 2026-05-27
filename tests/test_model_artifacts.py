import json
from pathlib import Path

import pytest

from crypto_trade_research.models.artifacts import (
    ExpectedRidgeArtifact,
    FeatureSchema,
    LinearProbabilityArtifact,
    ModelArtifact,
    MultifeatureRidgeArtifact,
    load_model_artifact,
    write_model_artifact,
)


def test_linear_probability_artifact_writes_loads_and_predicts_take_or_skip(
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    artifact_path = tmp_path / "artifact.json"

    written_hash = write_model_artifact(artifact_path, artifact)
    loaded = load_model_artifact(
        artifact_path,
        expected_feature_set_version="features.unit.v1",
        expected_feature_names=("return_1", "ma_2"),
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "crypto-trade.model-artifact.v1"
    assert payload["artifact_hash"] == written_hash
    assert len(written_hash) == 64
    assert "quantity" not in json.dumps(payload)
    assert loaded.artifact_hash == written_hash

    take = loaded.predict({"return_1": 0.05, "ma_2": 100.0})
    skip = loaded.predict({"return_1": -0.05, "ma_2": 100.0})
    assert take.recommended_action == "take"
    assert skip.recommended_action == "skip"
    assert 0 <= take.target_before_stop_probability <= 1


def test_model_artifact_loader_fails_closed_on_feature_schema_mismatch(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.json"
    write_model_artifact(artifact_path, _artifact())

    with pytest.raises(ValueError, match="feature schema mismatch"):
        load_model_artifact(
            artifact_path,
            expected_feature_set_version="features.other.v1",
            expected_feature_names=("return_1", "ma_2"),
        )

    with pytest.raises(ValueError, match="feature schema mismatch"):
        load_model_artifact(
            artifact_path,
            expected_feature_set_version="features.unit.v1",
            expected_feature_names=("return_1",),
        )


def test_model_artifact_loader_rejects_forbidden_order_authority_fields(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.json"
    write_model_artifact(artifact_path, _artifact())
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["model"]["quantity"] = 1.5
    artifact_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="forbidden ML authority field"):
        load_model_artifact(artifact_path)


def test_multifeature_ridge_artifact_writes_loads_and_fails_closed(tmp_path: Path) -> None:
    artifact = ModelArtifact(
        model_id="unit_multifeature",
        model_version="20260526T070000Z",
        model=MultifeatureRidgeArtifact(
            feature_names=("return_1", "risk_on_score_2"),
            means={"return_1": 0.0, "risk_on_score_2": 0.5},
            standard_deviations={"return_1": 0.02, "risk_on_score_2": 0.25},
            intercept=0.0,
            weights={"return_1": 1.0, "risk_on_score_2": 0.5},
            probability_threshold=0.55,
        ),
        feature_schema=FeatureSchema(
            feature_set_version="features.unit.v1",
            feature_names=("return_1", "risk_on_score_2", "ma_2"),
        ),
        preprocessing={"missing_value_policy": "fail_closed"},
        calibration={"method": "validation_threshold_v1"},
        dataset_manifest_path="data/generated/unit/manifest.json",
        training_data_hash="sha256:unit",
        research_git_commit="unitcommit",
        dependency_versions={"python": "3.12", "pyarrow": "unit"},
        created_at="2026-05-26T07:00:00Z",
    )
    artifact_path = tmp_path / "multifeature.json"

    write_model_artifact(artifact_path, artifact)
    loaded = load_model_artifact(artifact_path)

    take = loaded.predict({"return_1": 0.04, "risk_on_score_2": 0.75, "ma_2": 100.0})
    skip = loaded.predict({"return_1": -0.04, "risk_on_score_2": 0.25, "ma_2": 100.0})
    missing = loaded.predict({"return_1": 0.04, "ma_2": 100.0})
    assert take.recommended_action == "take"
    assert skip.recommended_action == "skip"
    assert missing.recommended_action == "skip"
    assert missing.reason_codes == ("missing_feature",)


def test_model_artifact_can_embed_expected_r_model_for_paper_ranking(tmp_path: Path) -> None:
    artifact = ModelArtifact(
        model_id="unit_expected_r",
        model_version="20260527T070000Z",
        model=MultifeatureRidgeArtifact(
            feature_names=("return_1",),
            means={"return_1": 0.0},
            standard_deviations={"return_1": 0.02},
            intercept=0.0,
            weights={"return_1": 1.0},
            probability_threshold=0.55,
        ),
        expected_r_model=ExpectedRidgeArtifact(
            feature_names=("return_1",),
            means={"return_1": 0.0},
            standard_deviations={"return_1": 0.02},
            intercept=-0.1,
            weights={"return_1": 0.2},
            expected_r_threshold=-0.2,
        ),
        feature_schema=FeatureSchema(
            feature_set_version="features.unit.v1",
            feature_names=("return_1",),
        ),
        preprocessing={"missing_value_policy": "fail_closed"},
        calibration={"method": "validation_threshold_v1"},
        dataset_manifest_path="data/generated/unit/manifest.json",
        training_data_hash="sha256:unit",
        research_git_commit="unitcommit",
        dependency_versions={"python": "3.12", "pyarrow": "unit"},
        created_at="2026-05-27T07:00:00Z",
    )
    artifact_path = tmp_path / "expected_r.json"

    write_model_artifact(artifact_path, artifact)
    loaded = load_model_artifact(artifact_path)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    prediction = loaded.predict({"return_1": 0.02})
    assert payload["expected_r_model"]["model_type"] == "ridge_expected_r"
    assert loaded.expected_r_model is not None
    assert prediction.expected_r == pytest.approx(0.1)


def _artifact() -> ModelArtifact:
    return ModelArtifact(
        model_id="unit_linear_probability",
        model_version="20260526T070000Z",
        model=LinearProbabilityArtifact(
            feature_name="return_1",
            threshold=0.0,
            positive_direction=1,
            probability_threshold=0.55,
        ),
        feature_schema=FeatureSchema(
            feature_set_version="features.unit.v1",
            feature_names=("return_1", "ma_2"),
        ),
        preprocessing={"missing_value_policy": "fail_closed"},
        calibration={"method": "logistic_margin_v1"},
        dataset_manifest_path="data/generated/unit/manifest.json",
        training_data_hash="sha256:unit",
        research_git_commit="unitcommit",
        dependency_versions={"python": "3.12", "pyarrow": "unit"},
        created_at="2026-05-26T07:00:00Z",
    )
