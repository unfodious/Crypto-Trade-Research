"""Batch orchestration and leaderboard summaries for baseline experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.experiments.runner import (
    BaselineExperimentConfig,
    BaselineExperimentInputs,
    BaselineExperimentResult,
    build_baseline_candidate_labels,
    build_baseline_features,
    build_baseline_labels,
    load_baseline_funding_rows,
    load_baseline_source_rows,
    run_baseline_experiment,
)
from crypto_trade_research.features import FeatureFrame, FeatureManifest, FeatureSpec
from crypto_trade_research.labels import LabelFrame, LabelManifest, LabelSpec

CACHE_SCHEMA_VERSION = "research.batch-artifact-cache.v1"


@dataclass(frozen=True, slots=True)
class BatchExperimentSpec:
    config_path: Path
    overrides: dict[str, object]


@dataclass(frozen=True, slots=True)
class BatchExperimentMatrix:
    experiments: tuple[BatchExperimentSpec, ...]
    leaderboard_path: Path
    markdown_path: Path
    cache_dir: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BatchExperimentMatrix:
        experiments = tuple(_experiment_spec(item) for item in payload.get("experiments", ()))
        if not experiments:
            raise ValueError("batch matrix must include at least one experiment config")
        leaderboard_path = Path(
            str(
                payload.get(
                    "leaderboard_path",
                    "data/generated/batch_experiments/leaderboard.json",
                )
            )
        )
        markdown_path = Path(str(payload.get("markdown_path", leaderboard_path.with_suffix(".md"))))
        cache_dir = Path(str(payload.get("cache_dir", "data/generated/research_cache")))
        return cls(
            experiments=experiments,
            leaderboard_path=leaderboard_path,
            markdown_path=markdown_path,
            cache_dir=cache_dir,
        )

    @classmethod
    def from_path(cls, path: Path) -> BatchExperimentMatrix:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class BatchExperimentRunResult:
    leaderboard_path: Path
    markdown_path: Path
    completed_count: int
    failed_count: int
    rows: tuple[dict[str, object], ...]


ExperimentRunner = Callable[[BaselineExperimentConfig], BaselineExperimentResult]


@dataclass(frozen=True, slots=True)
class _CachedSourceRows:
    dataset_manifest_path: Path
    rows: list[dict[str, object]]
    funding_rows: list[dict[str, object]]


class _ExperimentInputCache:
    def __init__(self, cache_dir: Path) -> None:
        self._sources: dict[tuple[object, ...], _CachedSourceRows] = {}
        self._features: dict[tuple[object, ...], FeatureFrame] = {}
        self._labels: dict[tuple[object, ...], LabelFrame] = {}
        self._cache_dir = cache_dir

    def inputs_for(self, config: BaselineExperimentConfig) -> BaselineExperimentInputs:
        source_key = _source_cache_key(config)
        source = self._sources.get(source_key)
        if source is None:
            dataset_manifest_path, source_rows = load_baseline_source_rows(config)
            funding_rows = load_baseline_funding_rows(config)
            source = _CachedSourceRows(dataset_manifest_path, source_rows, funding_rows)
            self._sources[source_key] = source

        feature_key = (
            *source_key,
            config.feature_set_version,
            config.rolling_window,
            config.higher_timeframes,
        )
        features = self._features.get(feature_key)
        if features is None:
            features = self._read_feature_cache(feature_key)
            if features is None:
                features = build_baseline_features(source.rows, config, source.funding_rows)
                self._write_feature_cache(feature_key, config, features)
            else:
                print(
                    f"[{config.experiment_name}] feature cache hit ({len(features.rows)} rows)",
                    flush=True,
                )
            self._features[feature_key] = features

        if config.label_generation_mode == "candidate_only":
            label_key = (
                *feature_key,
                *_label_cache_key(config),
                _candidate_setup_cache_key(config),
            )
            labels = self._labels.get(label_key)
            if labels is None:
                labels = self._read_label_cache(label_key)
                if labels is None:
                    labels = build_baseline_candidate_labels(source.rows, features.rows, config)
                    self._write_label_cache(label_key, config, labels)
                else:
                    print(
                        f"[{config.experiment_name}] candidate label cache hit "
                        f"({len(labels.rows)} rows)",
                        flush=True,
                    )
                self._labels[label_key] = labels
        else:
            label_key = (*source_key, *_label_cache_key(config))
            labels = self._labels.get(label_key)
            if labels is None:
                labels = build_baseline_labels(source.rows, config)
                self._labels[label_key] = labels

        return BaselineExperimentInputs(
            dataset_manifest_path=source.dataset_manifest_path,
            source_rows=source.rows,
            funding_rows=source.funding_rows,
            features=features,
            labels=labels,
        )

    def _read_feature_cache(
        self,
        key: tuple[object, ...],
    ) -> FeatureFrame | None:
        cache_path = _cache_artifact_path(self._cache_dir, "features", key)
        rows_path = cache_path / "rows.parquet"
        manifest_path = cache_path / "manifest.json"
        if not rows_path.exists() or not manifest_path.exists():
            return None
        payload = _read_json(manifest_path)
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        return FeatureFrame(
            rows=[dict(row) for row in pq.read_table(rows_path).to_pylist()],
            manifest=_feature_manifest_from_payload(dict(payload["feature_manifest"])),
        )

    def _write_feature_cache(
        self,
        key: tuple[object, ...],
        config: BaselineExperimentConfig,
        features: FeatureFrame,
    ) -> None:
        cache_path = _cache_artifact_path(self._cache_dir, "features", key)
        rows_path = cache_path / "rows.parquet"
        manifest_path = cache_path / "manifest.json"
        _write_parquet_atomic(rows_path, features.rows)
        _write_json_atomic(
            manifest_path,
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "kind": "features",
                "experiment_name": config.experiment_name,
                "created_at": _format_timestamp(datetime.now(UTC)),
                "cache_key": _cache_key(key),
                "row_count": len(features.rows),
                "feature_manifest": asdict(features.manifest),
            },
        )

    def _read_label_cache(
        self,
        key: tuple[object, ...],
    ) -> LabelFrame | None:
        cache_path = _cache_artifact_path(self._cache_dir, "candidate_labels", key)
        rows_path = cache_path / "rows.parquet"
        manifest_path = cache_path / "manifest.json"
        if not rows_path.exists() or not manifest_path.exists():
            return None
        payload = _read_json(manifest_path)
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        return LabelFrame(
            rows=[dict(row) for row in pq.read_table(rows_path).to_pylist()],
            manifest=_label_manifest_from_payload(dict(payload["label_manifest"])),
        )

    def _write_label_cache(
        self,
        key: tuple[object, ...],
        config: BaselineExperimentConfig,
        labels: LabelFrame,
    ) -> None:
        cache_path = _cache_artifact_path(self._cache_dir, "candidate_labels", key)
        rows_path = cache_path / "rows.parquet"
        manifest_path = cache_path / "manifest.json"
        _write_parquet_atomic(rows_path, labels.rows)
        _write_json_atomic(
            manifest_path,
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "kind": "candidate_labels",
                "experiment_name": config.experiment_name,
                "created_at": _format_timestamp(datetime.now(UTC)),
                "cache_key": _cache_key(key),
                "row_count": len(labels.rows),
                "label_manifest": asdict(labels.manifest),
            },
        )


def run_experiment_batch(
    matrix: BatchExperimentMatrix,
    *,
    runner: Callable[[object], object] = run_baseline_experiment,
) -> BatchExperimentRunResult:
    """Run each experiment config and write a failure-safe leaderboard."""

    rows: list[dict[str, object]] = []
    input_cache = _ExperimentInputCache(matrix.cache_dir)
    for index, spec in enumerate(matrix.experiments, start=1):
        raw_config: dict[str, object] = {}
        try:
            raw_config = _merged_config(
                json.loads(spec.config_path.read_text(encoding="utf-8")),
                spec.overrides,
            )
            experiment_name = str(raw_config.get("experiment_name") or spec.config_path.stem)
            print(
                f"[{index}/{len(matrix.experiments)}] running {experiment_name}",
                flush=True,
            )
            config = _runner_config(raw_config, runner)
            if runner is run_baseline_experiment:
                result = run_baseline_experiment(config, inputs=input_cache.inputs_for(config))
            else:
                result = runner(config)
            rows.append(
                leaderboard_row_from_record(
                    config=raw_config,
                    registry_record_path=Path(str(result.registry_record_path)),
                )
            )
            print(f"[{index}/{len(matrix.experiments)}] completed {experiment_name}", flush=True)
        except Exception as exc:  # noqa: BLE001 - batch mode must report per-config failures.
            rows.append(_failure_row(raw_config, spec.config_path, exc))
            print(f"[{index}/{len(matrix.experiments)}] failed: {exc}", flush=True)

    completed_count = sum(1 for row in rows if row["run_status"] == "completed")
    failed_count = len(rows) - completed_count
    payload = {
        "schema_version": "research.batch-leaderboard.v1",
        "generated_at": _format_timestamp(datetime.now(UTC)),
        "summary": {
            "completed": completed_count,
            "failed": failed_count,
            "total": len(rows),
        },
        "rows": rows,
    }
    _write_json(matrix.leaderboard_path, payload)
    matrix.markdown_path.parent.mkdir(parents=True, exist_ok=True)
    matrix.markdown_path.write_text(_markdown_leaderboard(rows), encoding="utf-8")
    return BatchExperimentRunResult(
        leaderboard_path=matrix.leaderboard_path,
        markdown_path=matrix.markdown_path,
        completed_count=completed_count,
        failed_count=failed_count,
        rows=tuple(rows),
    )


def leaderboard_row_from_record(
    *,
    config: dict[str, object],
    registry_record_path: Path,
) -> dict[str, object]:
    record = json.loads(registry_record_path.read_text(encoding="utf-8"))
    metrics = dict(record.get("metrics", {}))
    decision = dict(record.get("decision", {}))
    return {
        "experiment_name": str(config.get("experiment_name") or record["model"]["model_id"]),
        "run_status": "completed",
        "decision": str(decision.get("status", "unknown")),
        "failed_gates": [
            str(gate["name"])
            for gate in decision.get("gates", ())
            if not bool(gate.get("passed", False))
        ],
        "oos_model_average_r": _optional_float(metrics.get("average_r")),
        "oos_rule_only_average_r": _optional_float(metrics.get("rule_only_average_r")),
        "trade_count": _optional_int(metrics.get("trade_count")),
        "max_drawdown_pct": _optional_float(metrics.get("max_drawdown_pct")),
        "selected_probability_threshold": _optional_float(
            metrics.get("multifeature_probability_threshold")
        ),
        "selected_expected_r_threshold": _optional_float(metrics.get("expected_r_threshold")),
        "min_validation_trades_for_threshold": _optional_int(
            metrics.get("min_validation_trades_for_threshold")
        ),
        "primary_strategy": str(metrics.get("primary_strategy", "")),
        "symbol_coverage": _symbol_coverage(config),
        "artifact_hash": str(metrics.get("artifact_hash", "")),
        "registry_path": str(registry_record_path),
        "error": "",
    }


def _experiment_spec(item: object) -> BatchExperimentSpec:
    if isinstance(item, str):
        return BatchExperimentSpec(Path(item), {})
    payload = dict(item)
    return BatchExperimentSpec(
        config_path=Path(str(payload["config"])),
        overrides=dict(payload.get("overrides", {})),
    )


def _merged_config(
    base: dict[str, object],
    overrides: dict[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merged_config(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _runner_config(config: dict[str, object], runner: Callable[[object], object]) -> object:
    if runner is run_baseline_experiment:
        return BaselineExperimentConfig.from_dict(config)
    return SimpleNamespace(**config)


def _failure_row(
    config: dict[str, object],
    config_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "experiment_name": str(config.get("experiment_name") or config_path.stem),
        "run_status": "failed",
        "decision": "failed",
        "failed_gates": [],
        "oos_model_average_r": None,
        "oos_rule_only_average_r": None,
        "trade_count": None,
        "max_drawdown_pct": None,
        "selected_probability_threshold": None,
        "selected_expected_r_threshold": None,
        "min_validation_trades_for_threshold": None,
        "primary_strategy": "",
        "symbol_coverage": _symbol_coverage(config),
        "artifact_hash": "",
        "registry_path": "",
        "error": str(exc),
    }


def _symbol_coverage(config: dict[str, object]) -> str:
    candidate_setup = dict(config.get("candidate_setup", {}))
    candidate_symbols = candidate_setup.get("symbols")
    if candidate_symbols:
        return "candidate:" + ",".join(str(symbol).upper() for symbol in candidate_symbols)
    symbols = config.get("symbols")
    if not symbols:
        return "all"
    return ",".join(str(symbol).upper() for symbol in symbols)


def _source_cache_key(config: BaselineExperimentConfig) -> tuple[object, ...]:
    return (
        str(config.source_csv) if config.source_csv else None,
        _file_digest(config.source_csv) if config.source_csv else None,
        str(config.dataset_manifest_path) if config.dataset_manifest_path else None,
        _file_digest(config.dataset_manifest_path) if config.dataset_manifest_path else None,
        str(config.funding_manifest_path) if config.funding_manifest_path else None,
        _file_digest(config.funding_manifest_path) if config.funding_manifest_path else None,
        config.dataset_name,
        config.generator_version,
        config.symbols,
        config.timeframes,
    )


def _label_cache_key(config: BaselineExperimentConfig) -> tuple[object, ...]:
    label = config.label_config
    return (
        label.label_set_version,
        label.horizon_bars,
        label.side,
        label.stop_loss_pct,
        label.target_pct,
        label.cost_pct,
        label.flat_threshold_pct,
        label.target_stop_tie_breaker,
        label.exit_model,
        label.breakeven_activation_r,
        label.breakeven_lock_r,
        label.trailing_stop_r,
    )


def _candidate_setup_cache_key(config: BaselineExperimentConfig) -> tuple[object, ...]:
    setup = config.candidate_setup
    if setup is None:
        return ("all_samples", (), ())
    return (
        setup.name,
        setup.symbols,
        tuple((item.feature, item.operator, item.value) for item in setup.filters),
    )


def _cache_artifact_path(cache_dir: Path, kind: str, key: tuple[object, ...]) -> Path:
    return cache_dir / kind / _cache_key(key)


def _cache_key(key: tuple[object, ...]) -> str:
    normalized = json.dumps(key, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _file_digest(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _feature_manifest_from_payload(payload: dict[str, object]) -> FeatureManifest:
    return FeatureManifest(
        schema_version=str(payload["schema_version"]),
        feature_set_version=str(payload["feature_set_version"]),
        generator_name=str(payload["generator_name"]),
        row_count=int(payload["row_count"]),
        features=tuple(FeatureSpec(**dict(item)) for item in payload.get("features", ())),
    )


def _label_manifest_from_payload(payload: dict[str, object]) -> LabelManifest:
    return LabelManifest(
        schema_version=str(payload["schema_version"]),
        label_set_version=str(payload["label_set_version"]),
        generator_name=str(payload["generator_name"]),
        row_count=int(payload["row_count"]),
        horizon_bars=int(payload["horizon_bars"]),
        side=str(payload["side"]),
        labels=tuple(LabelSpec(**dict(item)) for item in payload.get("labels", ())),
    )


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _write_parquet_atomic(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.stem + ".tmp" + path.suffix)
    if not rows:
        pq.write_table(pa.Table.from_pylist(rows), temporary_path)
        temporary_path.replace(path)
        return

    writer = None
    try:
        for start in range(0, len(rows), 50_000):
            chunk = rows[start : start + 50_000]
            table = (
                pa.Table.from_pylist(chunk)
                if writer is None
                else pa.Table.from_pylist(chunk, schema=writer.schema)
            )
            if writer is None:
                writer = pq.ParquetWriter(temporary_path, table.schema)
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()
    temporary_path.replace(path)


def _markdown_leaderboard(rows: list[dict[str, object]]) -> str:
    lines = [
        "# Batch Experiment Leaderboard",
        "",
        "| Experiment | Run | Decision | Failed gates | Model avg R | Rule avg R | "
        "Trades | Max DD | Selected p | Selected E[R] | Min Val Trades | Primary | Symbols | "
        "Registry |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | "
        "--- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['experiment_name']} | "
            f"{row['run_status']} | "
            f"{row['decision']} | "
            f"{', '.join(row['failed_gates']) if row['failed_gates'] else '-'} | "
            f"{_fmt_metric(row['oos_model_average_r'])} | "
            f"{_fmt_metric(row['oos_rule_only_average_r'])} | "
            f"{row['trade_count'] if row['trade_count'] is not None else '-'} | "
            f"{_fmt_metric(row['max_drawdown_pct'])} | "
            f"{_fmt_metric(row['selected_probability_threshold'])} | "
            f"{_fmt_metric(row['selected_expected_r_threshold'])} | "
            f"{_fmt_optional_int(row['min_validation_trades_for_threshold'])} | "
            f"{row['primary_strategy'] or '-'} | "
            f"{row['symbol_coverage']} | "
            f"{row['registry_path'] or row['error']} |"
        )
    lines.extend(
        [
            "",
            "Backtest leaderboards are research evidence, not live trading approval.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt_metric(value: object) -> str:
    return f"{float(value):.4f}" if value is not None else "-"


def _fmt_optional_int(value: object) -> str:
    return str(value) if value is not None else "-"


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_experiment_batch(BatchExperimentMatrix.from_path(args.matrix))
    print(result.leaderboard_path)
    print(result.markdown_path)


if __name__ == "__main__":
    main()
