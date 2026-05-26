"""Batch orchestration and leaderboard summaries for baseline experiments."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from crypto_trade_research.experiments.runner import (
    BaselineExperimentConfig,
    BaselineExperimentResult,
    run_baseline_experiment,
)


@dataclass(frozen=True, slots=True)
class BatchExperimentSpec:
    config_path: Path
    overrides: dict[str, object]


@dataclass(frozen=True, slots=True)
class BatchExperimentMatrix:
    experiments: tuple[BatchExperimentSpec, ...]
    leaderboard_path: Path
    markdown_path: Path

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
        return cls(
            experiments=experiments,
            leaderboard_path=leaderboard_path,
            markdown_path=markdown_path,
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


def run_experiment_batch(
    matrix: BatchExperimentMatrix,
    *,
    runner: Callable[[object], object] = run_baseline_experiment,
) -> BatchExperimentRunResult:
    """Run each experiment config and write a failure-safe leaderboard."""

    rows: list[dict[str, object]] = []
    for spec in matrix.experiments:
        raw_config: dict[str, object] = {}
        try:
            raw_config = _merged_config(
                json.loads(spec.config_path.read_text(encoding="utf-8")),
                spec.overrides,
            )
            config = _runner_config(raw_config, runner)
            result = runner(config)
            rows.append(
                leaderboard_row_from_record(
                    config=raw_config,
                    registry_record_path=Path(str(result.registry_record_path)),
                )
            )
        except Exception as exc:  # noqa: BLE001 - batch mode must report per-config failures.
            rows.append(_failure_row(raw_config, spec.config_path, exc))

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
        "symbol_coverage": _symbol_coverage(config),
        "artifact_hash": "",
        "registry_path": "",
        "error": str(exc),
    }


def _symbol_coverage(config: dict[str, object]) -> str:
    symbols = config.get("symbols")
    if not symbols:
        return "all"
    return ",".join(str(symbol).upper() for symbol in symbols)


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _markdown_leaderboard(rows: list[dict[str, object]]) -> str:
    lines = [
        "# Batch Experiment Leaderboard",
        "",
        "| Experiment | Run | Decision | Failed gates | Model avg R | Rule avg R | "
        "Trades | Max DD | Symbols | Registry |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
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
