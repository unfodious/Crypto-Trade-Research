"""Versioned model artifact serialization and fail-closed loading."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

ARTIFACT_SCHEMA_VERSION = "crypto-trade.model-artifact.v1"

_FORBIDDEN_ML_AUTHORITY_FIELDS = {
    "leverage",
    "order_size",
    "position_size",
    "quantity",
    "order_quantity",
    "notional",
    "order_notional",
}

_FORBIDDEN_SECRET_FIELDS = {
    "api_key",
    "api_secret",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
}


@dataclass(frozen=True, slots=True)
class FeatureSchema:
    feature_set_version: str
    feature_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LinearProbabilityArtifact:
    feature_name: str
    threshold: float
    positive_direction: int
    probability_threshold: float
    model_type: str = "linear_probability_threshold"


@dataclass(frozen=True, slots=True)
class ModelArtifactPrediction:
    target_before_stop_probability: float
    recommended_action: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    model_id: str
    model_version: str
    model: LinearProbabilityArtifact
    feature_schema: FeatureSchema
    preprocessing: dict[str, object]
    calibration: dict[str, object]
    dataset_manifest_path: str
    training_data_hash: str
    research_git_commit: str
    dependency_versions: dict[str, str]
    created_at: str
    artifact_hash: str | None = None

    def predict(self, feature_values: dict[str, float]) -> ModelArtifactPrediction:
        for feature_name in self.feature_schema.feature_names:
            if feature_name not in feature_values:
                return ModelArtifactPrediction(
                    target_before_stop_probability=0.0,
                    recommended_action="skip",
                    reason_codes=("missing_feature",),
                )
        raw_value = float(feature_values[self.model.feature_name])
        margin = (
            raw_value - self.model.threshold
            if self.model.positive_direction >= 0
            else self.model.threshold - raw_value
        )
        probability = 1 / (1 + math.exp(-10 * margin))
        if probability >= self.model.probability_threshold:
            return ModelArtifactPrediction(
                target_before_stop_probability=probability,
                recommended_action="take",
                reason_codes=("probability_above_threshold",),
            )
        return ModelArtifactPrediction(
            target_before_stop_probability=probability,
            recommended_action="skip",
            reason_codes=("probability_below_threshold",),
        )


def write_model_artifact(path: Path, artifact: ModelArtifact) -> str:
    """Write a canonical JSON artifact and return its SHA-256 hash."""

    _validate_artifact(artifact)
    payload = _artifact_payload(artifact, artifact_hash=None)
    artifact_hash = _payload_hash(payload)
    payload["artifact_hash"] = artifact_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact_hash


def load_model_artifact(
    path: Path,
    expected_feature_set_version: str | None = None,
    expected_feature_names: tuple[str, ...] | None = None,
) -> ModelArtifact:
    """Load and validate a model artifact, failing closed on mismatch or tampering."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    _reject_forbidden_fields(payload)
    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {ARTIFACT_SCHEMA_VERSION}")
    expected_hash = str(payload.get("artifact_hash", ""))
    if not expected_hash:
        raise ValueError("artifact_hash is required")
    hash_payload = dict(payload)
    hash_payload["artifact_hash"] = None
    actual_hash = _payload_hash(hash_payload)
    if actual_hash != expected_hash:
        raise ValueError("artifact_hash mismatch")

    artifact = _artifact_from_payload(payload)
    _validate_artifact(artifact)
    if expected_feature_set_version is not None or expected_feature_names is not None:
        _validate_expected_feature_schema(
            artifact,
            expected_feature_set_version,
            expected_feature_names,
        )
    return artifact


def _artifact_payload(
    artifact: ModelArtifact,
    artifact_hash: str | None,
) -> dict[str, object]:
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "model_id": artifact.model_id,
        "model_version": artifact.model_version,
        "model": asdict(artifact.model),
        "feature_schema": asdict(artifact.feature_schema),
        "preprocessing": artifact.preprocessing,
        "calibration": artifact.calibration,
        "dataset_manifest_path": artifact.dataset_manifest_path,
        "training_data_hash": artifact.training_data_hash,
        "research_git_commit": artifact.research_git_commit,
        "dependency_versions": artifact.dependency_versions,
        "created_at": artifact.created_at,
        "authority": {
            "allowed_actions": ["take", "skip"],
        },
        "artifact_hash": artifact_hash,
    }


def _artifact_from_payload(payload: dict[str, Any]) -> ModelArtifact:
    feature_schema = payload["feature_schema"]
    artifact = ModelArtifact(
        model_id=str(payload["model_id"]),
        model_version=str(payload["model_version"]),
        model=LinearProbabilityArtifact(**payload["model"]),
        feature_schema=FeatureSchema(
            feature_set_version=str(feature_schema["feature_set_version"]),
            feature_names=tuple(feature_schema["feature_names"]),
        ),
        preprocessing=dict(payload["preprocessing"]),
        calibration=dict(payload["calibration"]),
        dataset_manifest_path=str(payload["dataset_manifest_path"]),
        training_data_hash=str(payload["training_data_hash"]),
        research_git_commit=str(payload["research_git_commit"]),
        dependency_versions={str(k): str(v) for k, v in payload["dependency_versions"].items()},
        created_at=str(payload["created_at"]),
        artifact_hash=str(payload["artifact_hash"]),
    )
    return replace(artifact, artifact_hash=str(payload["artifact_hash"]))


def _validate_artifact(artifact: ModelArtifact) -> None:
    required_strings = {
        "model_id": artifact.model_id,
        "model_version": artifact.model_version,
        "feature_set_version": artifact.feature_schema.feature_set_version,
        "dataset_manifest_path": artifact.dataset_manifest_path,
        "training_data_hash": artifact.training_data_hash,
        "research_git_commit": artifact.research_git_commit,
        "created_at": artifact.created_at,
    }
    missing = [name for name, value in required_strings.items() if not value.strip()]
    if missing:
        raise ValueError("missing required artifact metadata: " + ", ".join(missing))
    if not artifact.feature_schema.feature_names:
        raise ValueError("feature_names must not be empty")
    if artifact.model.feature_name not in artifact.feature_schema.feature_names:
        raise ValueError("model feature_name must be present in feature_schema")
    if artifact.model.positive_direction not in {-1, 1}:
        raise ValueError("positive_direction must be -1 or 1")
    if not 0 <= artifact.model.probability_threshold <= 1:
        raise ValueError("probability_threshold must be between 0 and 1")
    if not artifact.preprocessing:
        raise ValueError("preprocessing metadata must not be empty")
    if not artifact.calibration:
        raise ValueError("calibration metadata must not be empty")
    if not artifact.dependency_versions:
        raise ValueError("dependency_versions must not be empty")
    _reject_forbidden_fields(_artifact_payload(artifact, artifact_hash=artifact.artifact_hash))


def _validate_expected_feature_schema(
    artifact: ModelArtifact,
    expected_feature_set_version: str | None,
    expected_feature_names: tuple[str, ...] | None,
) -> None:
    if (
        expected_feature_set_version is not None
        and artifact.feature_schema.feature_set_version != expected_feature_set_version
    ):
        raise ValueError("feature schema mismatch")
    if (
        expected_feature_names is not None
        and artifact.feature_schema.feature_names != expected_feature_names
    ):
        raise ValueError("feature schema mismatch")


def _payload_hash(payload: dict[str, object]) -> str:
    content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _reject_forbidden_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in _FORBIDDEN_ML_AUTHORITY_FIELDS:
                raise ValueError(f"forbidden ML authority field at {path}.{key}")
            if normalized_key in _FORBIDDEN_SECRET_FIELDS:
                raise ValueError(f"forbidden secret field at {path}.{key}")
            _reject_forbidden_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_fields(item, f"{path}[{index}]")
