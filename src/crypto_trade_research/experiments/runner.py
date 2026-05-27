"""End-to-end baseline experiment runner for real or sample market datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.data.ingestion import (
    MarketDatasetConfig,
    generate_market_dataset,
)
from crypto_trade_research.features import FeatureConfig, FeatureFrame, generate_ohlcv_features
from crypto_trade_research.labels import (
    LabelConfig,
    LabelFrame,
    generate_trade_labels,
    generate_trade_labels_for_keys,
)
from crypto_trade_research.models import (
    BaselineConfig,
    ExpectedRidgeArtifact,
    FeatureSchema,
    ModelArtifact,
    ModelSample,
    MultifeatureRidgeArtifact,
    fit_ridge_expected_r_model,
    fit_ridge_probability_model,
    train_and_evaluate_baselines,
    write_model_artifact,
)
from crypto_trade_research.tracking import (
    CostAssumptions,
    ExperimentRecord,
    ModelVersion,
    PromotionGateInputs,
    PromotionGateThresholds,
    TimeWindow,
    evaluate_promotion_gates,
    write_experiment_record,
    write_promotion_checklist,
)


@dataclass(frozen=True, slots=True)
class TrainingTarget:
    mode: str = "target_before_stop"
    max_adverse_r_floor: float | None = None
    min_realized_r: float = 0.0


@dataclass(frozen=True, slots=True)
class BaselineExperimentConfig:
    experiment_name: str
    output_dir: Path
    registry_dir: Path
    dataset_name: str
    generator_version: str
    feature_set_version: str
    rolling_window: int
    decision_feature: str
    label_config: LabelConfig
    train_end: datetime
    validation_end: datetime
    test_end: datetime
    cost_assumptions: CostAssumptions
    higher_timeframes: tuple[str, ...] = ()
    source_csv: Path | None = None
    dataset_manifest_path: Path | None = None
    funding_manifest_path: Path | None = None
    generated_at: datetime | None = None
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    split_strategy: str = "chronological"
    probability_threshold: float = 0.5
    initial_equity: float = 10_000
    risk_per_trade_pct: float = 0.01
    research_git_commit: str = "unknown"
    promotion_gate_thresholds: PromotionGateThresholds = PromotionGateThresholds()
    candidate_setup: CandidateSetup | None = None
    training_target: TrainingTarget = field(default_factory=TrainingTarget)
    max_trades_per_symbol: int | None = None
    max_trades_per_decision_time: int | None = None
    loss_cooldown_signals: int = 0
    label_generation_mode: str = "full"
    include_trade_details: bool = True
    probability_threshold_candidates: tuple[float, ...] = (
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
    )
    min_validation_trades_for_threshold: int = 1
    expected_r_threshold_candidates: tuple[float, ...] = (
        0.00,
        0.05,
        0.10,
        0.20,
        0.30,
        0.50,
    )
    ranking_top_n_values: tuple[int, ...] = ()
    primary_strategy: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BaselineExperimentConfig:
        feature = dict(payload["feature"])
        label = dict(payload["label"])
        splits = dict(payload["splits"])
        baseline = dict(payload.get("baseline", {}))
        costs = dict(payload.get("cost_assumptions", {}))
        promotion_gates = dict(payload.get("promotion_gates", {}))
        risk_controls = dict(payload.get("risk_controls", {}))
        memory = dict(payload.get("memory", {}))
        reporting = dict(payload.get("reporting", {}))
        source_csv = payload.get("source_csv")
        dataset_manifest_path = payload.get("dataset_manifest_path")
        funding_manifest_path = payload.get("funding_manifest_path")
        return cls(
            experiment_name=str(payload["experiment_name"]),
            output_dir=Path(str(payload["output_dir"])),
            registry_dir=Path(str(payload["registry_dir"])),
            dataset_name=str(payload.get("dataset_name", payload["experiment_name"])),
            generator_version=str(payload.get("generator_version", "baseline.runner.v1")),
            generated_at=_parse_timestamp_optional(payload.get("generated_at")),
            source_csv=Path(str(source_csv)) if source_csv else None,
            dataset_manifest_path=(
                Path(str(dataset_manifest_path)) if dataset_manifest_path else None
            ),
            funding_manifest_path=(
                Path(str(funding_manifest_path)) if funding_manifest_path else None
            ),
            symbols=tuple(str(symbol).upper() for symbol in payload.get("symbols", ())),
            timeframes=tuple(str(timeframe).lower() for timeframe in payload.get("timeframes", ())),
            feature_set_version=str(feature["feature_set_version"]),
            rolling_window=int(feature.get("rolling_window", 20)),
            decision_feature=str(feature["decision_feature"]),
            higher_timeframes=tuple(
                str(timeframe).lower() for timeframe in feature.get("higher_timeframes", ())
            ),
            label_config=LabelConfig(
                label_set_version=str(label["label_set_version"]),
                horizon_bars=int(label["horizon_bars"]),
                side=str(label["side"]),
                stop_loss_pct=float(label["stop_loss_pct"]),
                target_pct=float(label["target_pct"]),
                cost_pct=float(label["cost_pct"]),
                flat_threshold_pct=float(label["flat_threshold_pct"]),
                target_stop_tie_breaker=str(label.get("target_stop_tie_breaker", "stop_first")),
                exit_model=str(label.get("exit_model", "fixed_target_stop")),
                breakeven_activation_r=_optional_float(label.get("breakeven_activation_r")),
                breakeven_lock_r=float(label.get("breakeven_lock_r", 0.0)),
                trailing_stop_r=_optional_float(label.get("trailing_stop_r")),
            ),
            split_strategy=str(splits.get("strategy", "chronological")),
            train_end=_parse_timestamp(str(splits["train_end"])),
            validation_end=_parse_timestamp(str(splits["validation_end"])),
            test_end=_parse_timestamp(str(splits["test_end"])),
            probability_threshold=float(baseline.get("probability_threshold", 0.5)),
            initial_equity=float(baseline.get("initial_equity", 10_000)),
            risk_per_trade_pct=float(baseline.get("risk_per_trade_pct", 0.01)),
            probability_threshold_candidates=tuple(
                float(value)
                for value in baseline.get(
                    "probability_threshold_candidates",
                    (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70),
                )
            ),
            min_validation_trades_for_threshold=int(
                baseline.get("min_validation_trades_for_threshold", 1)
            ),
            expected_r_threshold_candidates=tuple(
                float(value)
                for value in baseline.get(
                    "expected_r_threshold_candidates",
                    (0.00, 0.05, 0.10, 0.20, 0.30, 0.50),
                )
            ),
            ranking_top_n_values=tuple(
                int(value) for value in baseline.get("ranking_top_n_values", ())
            ),
            primary_strategy=(
                str(baseline["primary_strategy"])
                if baseline.get("primary_strategy") is not None
                else None
            ),
            cost_assumptions=CostAssumptions(
                fee_bps=float(costs.get("fee_bps", 0.0)),
                slippage_bps=float(costs.get("slippage_bps", 0.0)),
                funding_bps=float(costs.get("funding_bps", 0.0)),
                notes=str(costs.get("notes", "")),
            ),
            research_git_commit=str(payload.get("research_git_commit") or _git_commit()),
            promotion_gate_thresholds=PromotionGateThresholds(
                min_walk_forward_average_r=float(
                    promotion_gates.get("min_walk_forward_average_r", 0.0)
                ),
                min_oos_trade_count=int(promotion_gates.get("min_oos_trade_count", 10)),
                max_drawdown_pct=float(promotion_gates.get("max_drawdown_pct", 0.0)),
                max_drawdown_duration_bars=int(
                    promotion_gates.get("max_drawdown_duration_bars", 0)
                ),
                require_leakage_checks=bool(promotion_gates.get("require_leakage_checks", True)),
                require_stability_checks=bool(
                    promotion_gates.get("require_stability_checks", True)
                ),
                require_paper_trading_plan=bool(
                    promotion_gates.get("require_paper_trading_plan", True)
                ),
            ),
            candidate_setup=_candidate_setup_from_payload(payload.get("candidate_setup")),
            training_target=_training_target_from_payload(payload.get("training_target")),
            max_trades_per_symbol=_optional_int(risk_controls.get("max_trades_per_symbol")),
            max_trades_per_decision_time=_optional_int(
                risk_controls.get("max_trades_per_decision_time")
            ),
            loss_cooldown_signals=int(risk_controls.get("loss_cooldown_signals", 0)),
            label_generation_mode=str(memory.get("label_generation_mode", "full")),
            include_trade_details=bool(reporting.get("include_trade_details", True)),
        )


@dataclass(frozen=True, slots=True)
class CandidateSetupFilter:
    feature: str
    operator: str
    value: float


@dataclass(frozen=True, slots=True)
class CandidateSetup:
    name: str
    filters: tuple[CandidateSetupFilter, ...]


@dataclass(frozen=True, slots=True)
class BaselineExperimentResult:
    dataset_manifest_path: Path
    features_path: Path
    labels_path: Path
    baseline_report_path: Path
    baseline_markdown_path: Path
    model_artifact_path: Path
    promotion_checklist_path: Path
    registry_record_path: Path


@dataclass(frozen=True, slots=True)
class BaselineExperimentInputs:
    dataset_manifest_path: Path
    source_rows: list[dict[str, object]]
    funding_rows: list[dict[str, object]]
    features: FeatureFrame
    labels: LabelFrame


def load_baseline_source_rows(
    config: BaselineExperimentConfig,
) -> tuple[Path, list[dict[str, object]]]:
    """Load and filter the market rows for a baseline experiment config."""

    _log_progress(config, "loading source rows")
    dataset_manifest_path = _dataset_manifest_path(config)
    source_rows = pq.read_table(_cleaned_dataset_path(dataset_manifest_path)).to_pylist()
    source_rows = _filter_rows(source_rows, config)
    if not source_rows:
        raise ValueError("dataset filters produced no market rows")
    _log_progress(config, f"loaded {len(source_rows)} source rows")
    return dataset_manifest_path, source_rows


def load_baseline_funding_rows(config: BaselineExperimentConfig) -> list[dict[str, object]]:
    """Load optional point-in-time funding rows for feature generation."""

    if config.funding_manifest_path is None:
        return []
    _log_progress(config, "loading funding rows")
    funding_rows = pq.read_table(_cleaned_dataset_path(config.funding_manifest_path)).to_pylist()
    _log_progress(config, f"loaded {len(funding_rows)} funding rows")
    return funding_rows


def build_baseline_features(
    source_rows: list[dict[str, object]],
    config: BaselineExperimentConfig,
    funding_rows: list[dict[str, object]] | None = None,
) -> FeatureFrame:
    """Build point-in-time features for a baseline experiment config."""

    _log_progress(config, "building features")
    features = generate_ohlcv_features(
        source_rows,
        FeatureConfig(
            feature_set_version=config.feature_set_version,
            rolling_window=config.rolling_window,
            higher_timeframes=config.higher_timeframes,
        ),
        funding_rate_rows=funding_rows,
    )
    _log_progress(config, f"built {len(features.rows)} feature rows")
    return features


def build_baseline_labels(
    source_rows: list[dict[str, object]],
    config: BaselineExperimentConfig,
) -> LabelFrame:
    """Build supervised trade outcome labels for a baseline experiment config."""

    _log_progress(config, "building labels")
    labels = generate_trade_labels(source_rows, config.label_config)
    _log_progress(config, f"built {len(labels.rows)} label rows")
    return labels


def build_baseline_candidate_labels(
    source_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    config: BaselineExperimentConfig,
) -> LabelFrame:
    """Build supervised labels only for predeclared candidate feature rows."""

    _log_progress(config, "building candidate-only labels")
    candidate_keys = _candidate_feature_keys(feature_rows, config)
    labels = generate_trade_labels_for_keys(source_rows, config.label_config, candidate_keys)
    _log_progress(config, f"built {len(labels.rows)} candidate-only label rows")
    return labels


def prepare_baseline_experiment_inputs(
    config: BaselineExperimentConfig,
) -> BaselineExperimentInputs:
    """Load source rows and generate reusable feature/label frames."""

    dataset_manifest_path, source_rows = load_baseline_source_rows(config)
    funding_rows = load_baseline_funding_rows(config)
    features = build_baseline_features(source_rows, config, funding_rows)
    labels = (
        build_baseline_candidate_labels(source_rows, features.rows, config)
        if config.label_generation_mode == "candidate_only"
        else build_baseline_labels(source_rows, config)
    )
    return BaselineExperimentInputs(
        dataset_manifest_path=dataset_manifest_path,
        source_rows=source_rows,
        funding_rows=funding_rows,
        features=features,
        labels=labels,
    )


def run_baseline_experiment(
    config: BaselineExperimentConfig,
    *,
    inputs: BaselineExperimentInputs | None = None,
) -> BaselineExperimentResult:
    """Run dataset ingestion, feature generation, labels, baselines, and registry capture."""

    _validate_config(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    prepared_inputs = inputs or prepare_baseline_experiment_inputs(config)
    dataset_manifest_path = prepared_inputs.dataset_manifest_path
    features = prepared_inputs.features
    labels = prepared_inputs.labels
    samples = _build_samples(features.rows, labels.rows, config)
    samples = _apply_candidate_setup(samples, config.candidate_setup)
    if not samples:
        raise ValueError("no trainable samples after warmup and label filtering")
    _log_progress(config, f"training/evaluating {len(samples)} samples")

    feature_names = _feature_names(features.rows)
    baseline_report = train_and_evaluate_baselines(
        samples,
        BaselineConfig(
            feature_names=feature_names,
            decision_feature=config.decision_feature,
            train_end=config.train_end,
            validation_end=config.validation_end,
            test_end=config.test_end,
            probability_threshold=config.probability_threshold,
            initial_equity=config.initial_equity,
            risk_per_trade_pct=config.risk_per_trade_pct,
            max_trades_per_symbol=config.max_trades_per_symbol,
            max_trades_per_decision_time=config.max_trades_per_decision_time,
            loss_cooldown_signals=config.loss_cooldown_signals,
            probability_threshold_candidates=config.probability_threshold_candidates,
            min_validation_trades_for_threshold=config.min_validation_trades_for_threshold,
            expected_r_threshold_candidates=config.expected_r_threshold_candidates,
            ranking_top_n_values=config.ranking_top_n_values,
            primary_strategy=config.primary_strategy,
            training_target_name=_training_target_name(config.training_target),
        ),
    )
    _log_progress(config, "writing artifacts")

    features_path = config.output_dir / "features.parquet"
    labels_path = config.output_dir / "labels.parquet"
    feature_manifest_path = config.output_dir / "feature_manifest.json"
    label_manifest_path = config.output_dir / "label_manifest.json"
    baseline_report_path = config.output_dir / "baseline_report.json"
    baseline_markdown_path = config.output_dir / "baseline_report.md"
    model_artifact_path = config.output_dir / "model_artifact.json"
    promotion_checklist_path = config.output_dir / "promotion_checklist.json"
    feature_artifact_rows = (
        _candidate_feature_rows(features.rows, config)
        if config.label_generation_mode == "candidate_only"
        else features.rows
    )
    pq.write_table(pa.Table.from_pylist(feature_artifact_rows), features_path)
    pq.write_table(pa.Table.from_pylist(labels.rows), labels_path)
    feature_manifest_payload = asdict(features.manifest)
    if config.label_generation_mode == "candidate_only":
        feature_manifest_payload["row_count"] = len(feature_artifact_rows)
        feature_manifest_payload["artifact_scope"] = "candidate_only"
    _write_json(feature_manifest_path, feature_manifest_payload)
    _write_json(label_manifest_path, asdict(labels.manifest))

    baseline_payload = baseline_report.to_report_dict()
    model_artifact_hash = write_model_artifact(
        model_artifact_path,
        _model_artifact(
            config=config,
            samples=samples,
            feature_names=feature_names,
            dataset_manifest_path=dataset_manifest_path,
            baseline_payload=baseline_payload,
        ),
    )
    baseline_payload["metadata"] = {
        "experiment_name": config.experiment_name,
        "dataset_manifest_path": str(dataset_manifest_path),
        "feature_manifest_path": str(feature_manifest_path),
        "label_manifest_path": str(label_manifest_path),
        "model_artifact_path": str(model_artifact_path),
        "model_artifact_hash": model_artifact_hash,
        "promotion_checklist_path": str(promotion_checklist_path),
        "candidate_setup": _candidate_setup_payload(config.candidate_setup),
        "training_target": _training_target_payload(config.training_target),
        "sample_count": len(samples),
        "split_strategy": config.split_strategy,
        "label_generation_mode": config.label_generation_mode,
        "funding_manifest_path": str(config.funding_manifest_path)
        if config.funding_manifest_path is not None
        else None,
        "feature_artifact_row_count": len(feature_artifact_rows),
        "research_git_commit": config.research_git_commit,
        "risk_controls": _risk_controls_payload(config),
        "include_trade_details": config.include_trade_details,
    }
    if not config.include_trade_details:
        _remove_trade_details(baseline_payload)
    _write_json(baseline_report_path, baseline_payload)
    baseline_markdown_path.write_text(_markdown_report(baseline_payload), encoding="utf-8")

    experiment_record = _experiment_record(
        config,
        dataset_manifest_path,
        feature_names,
        baseline_payload,
        promotion_checklist_path,
    )
    write_promotion_checklist(promotion_checklist_path, experiment_record)
    registry_record_path = write_experiment_record(
        config.registry_dir,
        experiment_record,
    )
    _log_progress(config, "done")
    return BaselineExperimentResult(
        dataset_manifest_path=dataset_manifest_path,
        features_path=features_path,
        labels_path=labels_path,
        baseline_report_path=baseline_report_path,
        baseline_markdown_path=baseline_markdown_path,
        model_artifact_path=model_artifact_path,
        promotion_checklist_path=promotion_checklist_path,
        registry_record_path=registry_record_path,
    )


def _validate_config(config: BaselineExperimentConfig) -> None:
    if config.split_strategy != "chronological":
        raise ValueError("shuffled splits are not allowed for performance claims")
    if config.source_csv is None and config.dataset_manifest_path is None:
        raise ValueError("source_csv or dataset_manifest_path is required")
    if config.source_csv is not None and config.dataset_manifest_path is not None:
        raise ValueError("source_csv and dataset_manifest_path are mutually exclusive")
    if config.candidate_setup is not None and not config.candidate_setup.filters:
        raise ValueError("candidate_setup filters must not be empty")
    if not config.probability_threshold_candidates:
        raise ValueError("probability_threshold_candidates must not be empty")
    if any(threshold < 0 or threshold > 1 for threshold in config.probability_threshold_candidates):
        raise ValueError("probability_threshold_candidates must be between 0 and 1")
    if config.min_validation_trades_for_threshold <= 0:
        raise ValueError("min_validation_trades_for_threshold must be positive")
    if not config.expected_r_threshold_candidates:
        raise ValueError("expected_r_threshold_candidates must not be empty")
    if any(top_n <= 0 for top_n in config.ranking_top_n_values):
        raise ValueError("ranking_top_n_values must be positive")
    if config.label_generation_mode not in {"full", "candidate_only"}:
        raise ValueError("label_generation_mode must be full or candidate_only")
    if config.label_generation_mode == "candidate_only" and config.candidate_setup is None:
        raise ValueError("candidate_only label generation requires candidate_setup")
    if config.training_target.mode not in {
        "target_before_stop",
        "positive_r_after_costs",
        "clean_win_max_adverse_r",
    }:
        raise ValueError("unsupported training_target mode")
    if (
        config.training_target.mode == "clean_win_max_adverse_r"
        and config.training_target.max_adverse_r_floor is None
    ):
        raise ValueError("clean_win_max_adverse_r requires max_adverse_r_floor")


def _log_progress(config: BaselineExperimentConfig, message: str) -> None:
    print(f"[{config.experiment_name}] {message}", flush=True)


def _candidate_setup_from_payload(payload: object) -> CandidateSetup | None:
    if not payload:
        return None
    setup = dict(payload)
    return CandidateSetup(
        name=str(setup["name"]),
        filters=tuple(
            CandidateSetupFilter(
                feature=str(item["feature"]),
                operator=str(item["operator"]),
                value=float(item["value"]),
            )
            for item in setup.get("filters", ())
        ),
    )


def _candidate_setup_payload(setup: CandidateSetup | None) -> dict[str, object]:
    if setup is None:
        return {
            "name": "all_samples",
            "filters": [],
        }
    return asdict(setup)


def _training_target_from_payload(payload: object) -> TrainingTarget:
    if not payload:
        return TrainingTarget()
    target = dict(payload)
    return TrainingTarget(
        mode=str(target.get("mode", "target_before_stop")),
        max_adverse_r_floor=(
            float(target["max_adverse_r_floor"])
            if target.get("max_adverse_r_floor") is not None
            else None
        ),
        min_realized_r=float(target.get("min_realized_r", 0.0)),
    )


def _training_target_payload(target: TrainingTarget) -> dict[str, object]:
    return asdict(target)


def _training_target_name(target: TrainingTarget) -> str:
    if target.mode == "clean_win_max_adverse_r":
        return f"{target.mode}_gte_{target.max_adverse_r_floor:g}"
    if target.mode == "positive_r_after_costs":
        return f"{target.mode}_gte_{target.min_realized_r:g}"
    return target.mode


def _dataset_manifest_path(config: BaselineExperimentConfig) -> Path:
    if config.dataset_manifest_path is not None:
        return config.dataset_manifest_path
    if config.source_csv is None:
        raise ValueError("source_csv is required when dataset_manifest_path is absent")
    manifest = generate_market_dataset(
        MarketDatasetConfig(
            source_csv=config.source_csv,
            output_dir=config.output_dir / "dataset",
            dataset_name=config.dataset_name,
            generator_version=config.generator_version,
            generated_at=config.generated_at,
        )
    )
    return manifest.manifest_path


def _cleaned_dataset_path(dataset_manifest_path: Path) -> Path:
    payload = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    return Path(str(payload["cleaned_path"]))


def _filter_rows(
    rows: list[dict[str, object]],
    config: BaselineExperimentConfig,
) -> list[dict[str, object]]:
    symbols = set(config.symbols)
    timeframes = set(config.timeframes)
    return [
        row
        for row in rows
        if (not symbols or str(row["symbol"]).upper() in symbols)
        and (not timeframes or str(row["timeframe"]).lower() in timeframes)
    ]


def _build_samples(
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    config: BaselineExperimentConfig,
) -> list[ModelSample]:
    labels_by_key = {
        _sample_key(row): row
        for row in label_rows
        if isinstance(row.get("target_before_stop"), bool)
        and row.get("realized_r_after_costs") is not None
    }
    samples: list[ModelSample] = []
    for feature_row in feature_rows:
        label_row = labels_by_key.get(_sample_key(feature_row))
        decision_value = feature_row.get(config.decision_feature)
        if label_row is None or decision_value is None:
            continue
        feature_values = {
            name: float(value)
            for name, value in feature_row.items()
            if isinstance(value, int | float) and not isinstance(value, bool)
        }
        samples.append(
            ModelSample(
                decision_time=feature_row["decision_time"],
                symbol=str(feature_row["symbol"]),
                timeframe=str(feature_row["timeframe"]),
                side=str(label_row["side"]),
                features=feature_values,
                target_before_stop=_training_target_value(label_row, config.training_target),
                realized_r_after_costs=float(label_row["realized_r_after_costs"]),
            )
        )
    return samples


def _training_target_value(
    label_row: dict[str, object],
    target: TrainingTarget,
) -> bool:
    target_before_stop = bool(label_row["target_before_stop"])
    realized_r = float(label_row["realized_r_after_costs"])
    if target.mode == "target_before_stop":
        return target_before_stop
    if target.mode == "positive_r_after_costs":
        return realized_r >= target.min_realized_r
    if target.mode == "clean_win_max_adverse_r":
        mae = label_row.get("max_adverse_excursion_r")
        return (
            target_before_stop
            and realized_r >= target.min_realized_r
            and mae is not None
            and float(mae) >= float(target.max_adverse_r_floor)
        )
    raise ValueError(f"unsupported training_target mode: {target.mode}")


def _candidate_feature_keys(
    feature_rows: list[dict[str, object]],
    config: BaselineExperimentConfig,
) -> set[tuple[object, ...]]:
    return {
        _sample_key(feature_row) for feature_row in _candidate_feature_rows(feature_rows, config)
    }


def _candidate_feature_rows(
    feature_rows: list[dict[str, object]],
    config: BaselineExperimentConfig,
) -> list[dict[str, object]]:
    keys: set[tuple[object, ...]] = set()
    rows: list[dict[str, object]] = []
    for feature_row in feature_rows:
        if feature_row.get(config.decision_feature) is None:
            continue
        if config.candidate_setup is not None:
            feature_values = {
                name: float(value)
                for name, value in feature_row.items()
                if isinstance(value, int | float) and not isinstance(value, bool)
            }
            if not all(
                _matches_filter(feature_values, condition)
                for condition in config.candidate_setup.filters
            ):
                continue
        key = _sample_key(feature_row)
        if key in keys:
            continue
        keys.add(key)
        rows.append(feature_row)
    return rows


def _apply_candidate_setup(
    samples: list[ModelSample],
    setup: CandidateSetup | None,
) -> list[ModelSample]:
    if setup is None:
        return samples
    filtered = [
        sample
        for sample in samples
        if all(_matches_filter(sample.features, condition) for condition in setup.filters)
    ]
    if not filtered:
        raise ValueError("candidate_setup filters produced no trainable samples")
    return filtered


def _matches_filter(
    features: dict[str, float],
    condition: CandidateSetupFilter,
) -> bool:
    value = features.get(condition.feature)
    if value is None:
        return False
    if condition.operator == "<":
        return value < condition.value
    if condition.operator == "<=":
        return value <= condition.value
    if condition.operator == ">":
        return value > condition.value
    if condition.operator == ">=":
        return value >= condition.value
    if condition.operator == "==":
        return value == condition.value
    if condition.operator == "!=":
        return value != condition.value
    raise ValueError(f"unsupported candidate_setup operator: {condition.operator}")


def _sample_key(row: dict[str, object]) -> tuple[object, ...]:
    return (row["venue"], row["market_type"], row["symbol"], row["timeframe"], row["decision_time"])


def _feature_names(feature_rows: list[dict[str, object]]) -> tuple[str, ...]:
    excluded = {
        "schema_version",
        "feature_set_version",
        "venue",
        "market_type",
        "symbol",
        "timeframe",
        "decision_time",
        "source_window_start",
        "source_window_end",
        "source_available_at",
    }
    names: set[str] = set()
    for row in feature_rows:
        for name, value in row.items():
            if (
                name not in excluded
                and isinstance(value, int | float)
                and not isinstance(value, bool)
            ):
                names.add(name)
    return tuple(sorted(names))


def _model_artifact(
    config: BaselineExperimentConfig,
    samples: list[ModelSample],
    feature_names: tuple[str, ...],
    dataset_manifest_path: Path,
    baseline_payload: dict[str, Any],
) -> ModelArtifact:
    train_samples = [sample for sample in samples if sample.decision_time <= config.train_end]
    if not train_samples:
        raise ValueError("training split must not be empty")
    return ModelArtifact(
        model_id=config.experiment_name,
        model_version=_version(config.generated_at),
        model=_multifeature_ridge_artifact(train_samples, config, feature_names, baseline_payload),
        expected_r_model=_expected_r_artifact(
            train_samples, config, feature_names, baseline_payload
        ),
        feature_schema=FeatureSchema(
            feature_set_version=config.feature_set_version,
            feature_names=feature_names,
        ),
        preprocessing={
            "missing_value_policy": "fail_closed",
            "research_training_imputation": "train_mean",
            "research_training_target": _training_target_payload(config.training_target),
            "warmup_rows": "excluded_when_decision_feature_missing",
        },
        calibration={
            "method": "validation_threshold_v1",
            "probability_threshold": _multifeature_probability_threshold(baseline_payload),
            "min_validation_trades_for_threshold": config.min_validation_trades_for_threshold,
            "expected_r_threshold": float(
                baseline_payload["model_metadata"].get("expected_r_threshold", 0.0)
            ),
        },
        dataset_manifest_path=str(dataset_manifest_path),
        training_data_hash=_file_sha256(dataset_manifest_path),
        research_git_commit=config.research_git_commit,
        dependency_versions={
            "python": ">=3.11",
            "pyarrow": pa.__version__,
        },
        created_at=_format_timestamp(config.generated_at or datetime.now(UTC)),
    )


def _expected_r_artifact(
    samples: list[ModelSample],
    config: BaselineExperimentConfig,
    feature_names: tuple[str, ...],
    baseline_payload: dict[str, Any],
) -> ExpectedRidgeArtifact:
    model = fit_ridge_expected_r_model(
        samples,
        BaselineConfig(
            feature_names=feature_names,
            decision_feature=config.decision_feature,
            train_end=config.train_end,
            validation_end=config.validation_end,
            test_end=config.test_end,
            probability_threshold=config.probability_threshold,
            initial_equity=config.initial_equity,
            risk_per_trade_pct=config.risk_per_trade_pct,
            max_trades_per_symbol=config.max_trades_per_symbol,
            max_trades_per_decision_time=config.max_trades_per_decision_time,
            loss_cooldown_signals=config.loss_cooldown_signals,
            probability_threshold_candidates=config.probability_threshold_candidates,
            min_validation_trades_for_threshold=config.min_validation_trades_for_threshold,
            expected_r_threshold_candidates=config.expected_r_threshold_candidates,
            ranking_top_n_values=config.ranking_top_n_values,
            primary_strategy=config.primary_strategy,
            training_target_name=_training_target_name(config.training_target),
        ),
    )
    return ExpectedRidgeArtifact(
        feature_names=model.feature_names,
        means=model.means,
        standard_deviations=model.standard_deviations,
        intercept=model.intercept,
        weights=model.weights,
        expected_r_threshold=float(
            baseline_payload["model_metadata"].get("expected_r_threshold", 0.0)
        ),
    )


def _multifeature_ridge_artifact(
    samples: list[ModelSample],
    config: BaselineExperimentConfig,
    feature_names: tuple[str, ...],
    baseline_payload: dict[str, Any],
) -> MultifeatureRidgeArtifact:
    model = fit_ridge_probability_model(
        samples,
        BaselineConfig(
            feature_names=feature_names,
            decision_feature=config.decision_feature,
            train_end=config.train_end,
            validation_end=config.validation_end,
            test_end=config.test_end,
            probability_threshold=config.probability_threshold,
            initial_equity=config.initial_equity,
            risk_per_trade_pct=config.risk_per_trade_pct,
            max_trades_per_symbol=config.max_trades_per_symbol,
            max_trades_per_decision_time=config.max_trades_per_decision_time,
            loss_cooldown_signals=config.loss_cooldown_signals,
            probability_threshold_candidates=config.probability_threshold_candidates,
            min_validation_trades_for_threshold=config.min_validation_trades_for_threshold,
            expected_r_threshold_candidates=config.expected_r_threshold_candidates,
            ranking_top_n_values=config.ranking_top_n_values,
            primary_strategy=config.primary_strategy,
            training_target_name=_training_target_name(config.training_target),
        ),
    )
    return MultifeatureRidgeArtifact(
        feature_names=model.feature_names,
        means=model.means,
        standard_deviations=model.standard_deviations,
        intercept=model.intercept,
        weights=model.weights,
        probability_threshold=_multifeature_probability_threshold(baseline_payload),
    )


def _multifeature_probability_threshold(baseline_payload: dict[str, Any]) -> float:
    metadata = dict(baseline_payload.get("model_metadata", {}))
    return float(metadata.get("multifeature_probability_threshold", 0.5))


def _risk_controls_payload(config: BaselineExperimentConfig) -> dict[str, int | None]:
    return {
        "max_trades_per_symbol": config.max_trades_per_symbol,
        "max_trades_per_decision_time": config.max_trades_per_decision_time,
        "loss_cooldown_signals": config.loss_cooldown_signals,
    }


def _experiment_record(
    config: BaselineExperimentConfig,
    dataset_manifest_path: Path,
    feature_names: tuple[str, ...],
    baseline_payload: dict[str, Any],
    promotion_checklist_path: Path,
) -> ExperimentRecord:
    strategies = baseline_payload["strategies"]
    primary_strategy = str(
        dict(baseline_payload.get("model_metadata", {})).get(
            "primary_strategy",
            "multifeature_ridge_oos",
        )
    )
    model_metrics = strategies[primary_strategy]["metrics"]
    single_feature_metrics = strategies["linear_probability_oos"]["metrics"]
    rule_metrics = strategies["rule_only_oos"]["metrics"]
    naive_metrics = strategies["no_trade_oos"]["metrics"]
    gate_inputs = PromotionGateInputs(
        model_average_r=float(model_metrics["average_r"]),
        rule_only_average_r=float(rule_metrics["average_r"]),
        naive_average_r=float(naive_metrics["average_r"]),
        walk_forward_average_r=float(model_metrics["average_r"]),
        model_oos_trade_count=int(model_metrics["trade_count"]),
        max_drawdown_pct=float(model_metrics["max_drawdown_pct"]),
        max_drawdown_duration_bars=int(model_metrics["max_drawdown_duration"]),
        leakage_checks_passed=True,
        stability_checks_passed=False,
        paper_trading_plan_path="",
        thresholds=config.promotion_gate_thresholds,
    )
    return ExperimentRecord(
        model=ModelVersion(
            model_id=config.experiment_name,
            version=_version(config.generated_at),
            model_type="multifeature_ridge",
        ),
        research_git_commit=config.research_git_commit,
        dataset_manifest_path=str(dataset_manifest_path),
        dataset_manifest_version=config.dataset_name,
        feature_names=feature_names,
        feature_code_version=config.feature_set_version,
        label_config=asdict(config.label_config),
        train_window=TimeWindow(
            _format_timestamp(_first_split_start(baseline_payload)),
            _format_timestamp(config.train_end),
        ),
        validation_window=TimeWindow(
            _format_timestamp(config.train_end),
            _format_timestamp(config.validation_end),
        ),
        test_window=TimeWindow(
            _format_timestamp(config.validation_end),
            _format_timestamp(config.test_end),
        ),
        cost_assumptions=config.cost_assumptions,
        metrics={
            "average_r": float(model_metrics["average_r"]),
            "rule_only_average_r": float(rule_metrics["average_r"]),
            "naive_average_r": float(naive_metrics["average_r"]),
            "walk_forward_average_r": float(model_metrics["average_r"]),
            "single_feature_average_r": float(single_feature_metrics["average_r"]),
            "max_drawdown_pct": float(model_metrics["max_drawdown_pct"]),
            "max_drawdown_duration_bars": int(model_metrics["max_drawdown_duration"]),
            "trade_count": int(model_metrics["trade_count"]),
            "artifact_hash": str(baseline_payload["metadata"]["model_artifact_hash"]),
            "promotion_checklist_path": str(promotion_checklist_path),
            "candidate_setup_name": str(baseline_payload["metadata"]["candidate_setup"]["name"]),
            "candidate_sample_count": int(baseline_payload["metadata"]["sample_count"]),
            "training_target": str(baseline_payload["model_metadata"]["training_target"]),
            "primary_strategy": primary_strategy,
            "multifeature_probability_threshold": float(
                baseline_payload["model_metadata"]["multifeature_probability_threshold"]
            ),
            "expected_r_threshold": float(
                baseline_payload["model_metadata"].get("expected_r_threshold", 0.0)
            ),
            "min_validation_trades_for_threshold": int(
                baseline_payload["model_metadata"].get("min_validation_trades_for_threshold", 1)
            ),
        },
        walk_forward_report_path=str(Path(config.output_dir) / "baseline_report.json"),
        decision=evaluate_promotion_gates(gate_inputs),
        created_at=config.generated_at or datetime.now(UTC),
    )


def _first_split_start(baseline_payload: dict[str, Any]) -> datetime:
    return _parse_timestamp(str(baseline_payload["splits"][0]["start"]))


def _markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Baseline Experiment Report",
        "",
        f"Experiment: {payload['metadata']['experiment_name']}",
        f"Decision: {payload['decision']}",
        "",
        "## Out-of-Sample",
        "",
        "| Strategy | Trades | Average R | Total Return |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, report in payload["strategies"].items():
        if report["sample_scope"] != "validation_test":
            continue
        metrics = report["metrics"]
        lines.append(
            f"| {name} | {metrics['trade_count']} | "
            f"{metrics['average_r']:.4f} | {metrics['total_return_pct']:.4%} |"
        )
    lines.extend(
        [
            "",
            "## Validation Threshold Sweep",
            "",
            "| Threshold | Selected | Validation Trades | Validation Avg R | "
            "Max DD | Profit Factor |",
            "| ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["model_metadata"].get("validation_threshold_sweep", ()):
        lines.append(
            f"| {row['threshold']:.2f} | "
            f"{'yes' if row['selected'] else 'no'} | "
            f"{row['validation_trade_count']} | "
            f"{row['validation_average_r']:.4f} | "
            f"{row['validation_max_drawdown_pct']:.4%} | "
            f"{row['validation_profit_factor']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Expected-R Threshold Sweep",
            "",
            "| Threshold | Selected | Meets Exposure Floor | Validation Trades | "
            "Validation Avg R | Max DD | Profit Factor |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["model_metadata"].get("expected_r_validation_threshold_sweep", ()):
        lines.append(
            f"| {row['threshold']:.2f} | "
            f"{'yes' if row['selected'] else 'no'} | "
            f"{'yes' if row.get('meets_exposure_floor') else 'no'} | "
            f"{row['validation_trade_count']} | "
            f"{row['validation_average_r']:.4f} | "
            f"{row['validation_max_drawdown_pct']:.4%} | "
            f"{row['validation_profit_factor']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Top-N Ranking",
            "",
            "| Strategy | Trades | Average R | Max DD | Profit Factor |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["model_metadata"].get("ranking_comparison", ()):
        lines.append(
            f"| {row['strategy']} | "
            f"{row['trade_count']} | "
            f"{row['average_r']:.4f} | "
            f"{row['max_drawdown_pct']:.4%} | "
            f"{row['profit_factor']:.4f} |"
        )
    lines.extend(
        [
            "",
            "Backtest results are research evidence only, not live profitability claims.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _remove_trade_details(payload: dict[str, Any]) -> None:
    for strategy in payload.get("strategies", {}).values():
        if not isinstance(strategy, dict):
            continue
        trade_count = len(strategy.get("trades", ()))
        equity_point_count = len(strategy.get("equity_curve", ()))
        strategy["trade_detail_count"] = trade_count
        strategy["equity_curve_detail_count"] = equity_point_count
        strategy["trades"] = []
        strategy["equity_curve"] = []


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return _format_timestamp(value)
    return str(value)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _parse_timestamp_optional(value: object) -> datetime | None:
    return _parse_timestamp(str(value)) if value else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _version(generated_at: datetime | None) -> str:
    stamp = generated_at or datetime.now(UTC)
    return stamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = BaselineExperimentConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
    result = run_baseline_experiment(config)
    print(result.baseline_report_path)
    print(result.registry_record_path)


if __name__ == "__main__":
    main()
