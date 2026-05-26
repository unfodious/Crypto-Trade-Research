"""Baseline and experimental model training."""

from crypto_trade_research.models.artifacts import (
    FeatureSchema,
    LinearProbabilityArtifact,
    ModelArtifact,
    ModelArtifactPrediction,
    MultifeatureRidgeArtifact,
    load_model_artifact,
    write_model_artifact,
)
from crypto_trade_research.models.baselines import (
    BaselineComparisonReport,
    BaselineConfig,
    LinearProbabilityModel,
    ModelSample,
    TimeSplit,
    fit_ridge_probability_model,
    train_and_evaluate_baselines,
)

__all__ = [
    "BaselineComparisonReport",
    "BaselineConfig",
    "FeatureSchema",
    "LinearProbabilityModel",
    "LinearProbabilityArtifact",
    "ModelArtifact",
    "ModelArtifactPrediction",
    "ModelSample",
    "MultifeatureRidgeArtifact",
    "TimeSplit",
    "fit_ridge_probability_model",
    "load_model_artifact",
    "train_and_evaluate_baselines",
    "write_model_artifact",
]
