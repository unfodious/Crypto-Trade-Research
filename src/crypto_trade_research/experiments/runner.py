"""End-to-end baseline experiment runner for real or sample market datasets."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.data.ingestion import (
    MarketDatasetConfig,
    generate_market_dataset,
)
from crypto_trade_research.features import FeatureConfig, generate_ohlcv_features
from crypto_trade_research.labels import LabelConfig, generate_trade_labels
from crypto_trade_research.models import (
    BaselineConfig,
    ModelSample,
    train_and_evaluate_baselines,
)
from crypto_trade_research.tracking import (
    CostAssumptions,
    ExperimentRecord,
    ModelVersion,
    PromotionGateInputs,
    TimeWindow,
    evaluate_promotion_gates,
    write_experiment_record,
)


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
    source_csv: Path | None = None
    dataset_manifest_path: Path | None = None
    generated_at: datetime | None = None
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    split_strategy: str = "chronological"
    probability_threshold: float = 0.5
    initial_equity: float = 10_000
    risk_per_trade_pct: float = 0.01
    research_git_commit: str = "unknown"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BaselineExperimentConfig:
        feature = dict(payload["feature"])
        label = dict(payload["label"])
        splits = dict(payload["splits"])
        baseline = dict(payload.get("baseline", {}))
        costs = dict(payload.get("cost_assumptions", {}))
        source_csv = payload.get("source_csv")
        dataset_manifest_path = payload.get("dataset_manifest_path")
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
            symbols=tuple(str(symbol).upper() for symbol in payload.get("symbols", ())),
            timeframes=tuple(str(timeframe).lower() for timeframe in payload.get("timeframes", ())),
            feature_set_version=str(feature["feature_set_version"]),
            rolling_window=int(feature.get("rolling_window", 20)),
            decision_feature=str(feature["decision_feature"]),
            label_config=LabelConfig(
                label_set_version=str(label["label_set_version"]),
                horizon_bars=int(label["horizon_bars"]),
                side=str(label["side"]),
                stop_loss_pct=float(label["stop_loss_pct"]),
                target_pct=float(label["target_pct"]),
                cost_pct=float(label["cost_pct"]),
                flat_threshold_pct=float(label["flat_threshold_pct"]),
                target_stop_tie_breaker=str(label.get("target_stop_tie_breaker", "stop_first")),
            ),
            split_strategy=str(splits.get("strategy", "chronological")),
            train_end=_parse_timestamp(str(splits["train_end"])),
            validation_end=_parse_timestamp(str(splits["validation_end"])),
            test_end=_parse_timestamp(str(splits["test_end"])),
            probability_threshold=float(baseline.get("probability_threshold", 0.5)),
            initial_equity=float(baseline.get("initial_equity", 10_000)),
            risk_per_trade_pct=float(baseline.get("risk_per_trade_pct", 0.01)),
            cost_assumptions=CostAssumptions(
                fee_bps=float(costs.get("fee_bps", 0.0)),
                slippage_bps=float(costs.get("slippage_bps", 0.0)),
                funding_bps=float(costs.get("funding_bps", 0.0)),
                notes=str(costs.get("notes", "")),
            ),
            research_git_commit=str(payload.get("research_git_commit") or _git_commit()),
        )


@dataclass(frozen=True, slots=True)
class BaselineExperimentResult:
    dataset_manifest_path: Path
    features_path: Path
    labels_path: Path
    baseline_report_path: Path
    baseline_markdown_path: Path
    registry_record_path: Path


def run_baseline_experiment(config: BaselineExperimentConfig) -> BaselineExperimentResult:
    """Run dataset ingestion, feature generation, labels, baselines, and registry capture."""

    _validate_config(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    dataset_manifest_path = _dataset_manifest_path(config)
    source_rows = pq.read_table(_cleaned_dataset_path(dataset_manifest_path)).to_pylist()
    source_rows = _filter_rows(source_rows, config)
    if not source_rows:
        raise ValueError("dataset filters produced no market rows")

    features = generate_ohlcv_features(
        source_rows,
        FeatureConfig(
            feature_set_version=config.feature_set_version,
            rolling_window=config.rolling_window,
        ),
    )
    labels = generate_trade_labels(source_rows, config.label_config)
    samples = _build_samples(features.rows, labels.rows, config)
    if not samples:
        raise ValueError("no trainable samples after warmup and label filtering")

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
        ),
    )

    features_path = config.output_dir / "features.parquet"
    labels_path = config.output_dir / "labels.parquet"
    feature_manifest_path = config.output_dir / "feature_manifest.json"
    label_manifest_path = config.output_dir / "label_manifest.json"
    baseline_report_path = config.output_dir / "baseline_report.json"
    baseline_markdown_path = config.output_dir / "baseline_report.md"
    pq.write_table(pa.Table.from_pylist(features.rows), features_path)
    pq.write_table(pa.Table.from_pylist(labels.rows), labels_path)
    _write_json(feature_manifest_path, asdict(features.manifest))
    _write_json(label_manifest_path, asdict(labels.manifest))

    baseline_payload = baseline_report.to_report_dict()
    baseline_payload["metadata"] = {
        "experiment_name": config.experiment_name,
        "dataset_manifest_path": str(dataset_manifest_path),
        "feature_manifest_path": str(feature_manifest_path),
        "label_manifest_path": str(label_manifest_path),
        "sample_count": len(samples),
        "split_strategy": config.split_strategy,
        "research_git_commit": config.research_git_commit,
    }
    _write_json(baseline_report_path, baseline_payload)
    baseline_markdown_path.write_text(_markdown_report(baseline_payload), encoding="utf-8")

    registry_record_path = write_experiment_record(
        config.registry_dir,
        _experiment_record(config, dataset_manifest_path, feature_names, baseline_payload),
    )
    return BaselineExperimentResult(
        dataset_manifest_path=dataset_manifest_path,
        features_path=features_path,
        labels_path=labels_path,
        baseline_report_path=baseline_report_path,
        baseline_markdown_path=baseline_markdown_path,
        registry_record_path=registry_record_path,
    )


def _validate_config(config: BaselineExperimentConfig) -> None:
    if config.split_strategy != "chronological":
        raise ValueError("shuffled splits are not allowed for performance claims")
    if config.source_csv is None and config.dataset_manifest_path is None:
        raise ValueError("source_csv or dataset_manifest_path is required")
    if config.source_csv is not None and config.dataset_manifest_path is not None:
        raise ValueError("source_csv and dataset_manifest_path are mutually exclusive")


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
                target_before_stop=bool(label_row["target_before_stop"]),
                realized_r_after_costs=float(label_row["realized_r_after_costs"]),
            )
        )
    return samples


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


def _experiment_record(
    config: BaselineExperimentConfig,
    dataset_manifest_path: Path,
    feature_names: tuple[str, ...],
    baseline_payload: dict[str, Any],
) -> ExperimentRecord:
    strategies = baseline_payload["strategies"]
    model_metrics = strategies["linear_probability_oos"]["metrics"]
    rule_metrics = strategies["rule_only_oos"]["metrics"]
    naive_metrics = strategies["no_trade_oos"]["metrics"]
    gate_inputs = PromotionGateInputs(
        model_average_r=float(model_metrics["average_r"]),
        rule_only_average_r=float(rule_metrics["average_r"]),
        naive_average_r=float(naive_metrics["average_r"]),
        walk_forward_average_r=float(model_metrics["average_r"]),
        max_drawdown_pct=float(model_metrics["max_drawdown_pct"]),
        max_drawdown_duration_bars=int(model_metrics["max_drawdown_duration"]),
        max_allowed_drawdown_pct=0.0,
        max_allowed_drawdown_duration_bars=0,
        leakage_checks_passed=True,
        stability_checks_passed=False,
        paper_trading_plan_path="",
    )
    return ExperimentRecord(
        model=ModelVersion(
            model_id=config.experiment_name,
            version=_version(config.generated_at),
            model_type="linear_probability_threshold",
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
            "max_drawdown_pct": float(model_metrics["max_drawdown_pct"]),
            "max_drawdown_duration_bars": int(model_metrics["max_drawdown_duration"]),
            "trade_count": int(model_metrics["trade_count"]),
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


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return _format_timestamp(value)
    return str(value)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _parse_timestamp_optional(value: object) -> datetime | None:
    return _parse_timestamp(str(value)) if value else None


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
