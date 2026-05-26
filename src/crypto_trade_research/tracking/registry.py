"""Minimal JSON experiment registry for research-only model promotion."""

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

PromotionStatus = Literal["promote_to_paper_trading", "reject"]


@dataclass(frozen=True, slots=True)
class ModelVersion:
    model_id: str
    version: str
    model_type: str


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: str
    end: str


@dataclass(frozen=True, slots=True)
class CostAssumptions:
    fee_bps: float
    slippage_bps: float
    funding_bps: float
    notes: str


@dataclass(frozen=True, slots=True)
class PromotionGateResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    status: PromotionStatus
    reason: str
    gates: tuple[PromotionGateResult, ...]
    thresholds: dict[str, float | int | bool] = field(default_factory=dict)
    reviewed_by: str | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionGateThresholds:
    min_walk_forward_average_r: float = 0.0
    min_oos_trade_count: int = 10
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    require_leakage_checks: bool = True
    require_stability_checks: bool = True
    require_paper_trading_plan: bool = True


@dataclass(frozen=True, slots=True)
class PromotionGateInputs:
    model_average_r: float
    rule_only_average_r: float
    naive_average_r: float
    walk_forward_average_r: float
    model_oos_trade_count: int
    max_drawdown_pct: float
    max_drawdown_duration_bars: int
    leakage_checks_passed: bool
    stability_checks_passed: bool
    paper_trading_plan_path: str
    thresholds: PromotionGateThresholds = field(default_factory=PromotionGateThresholds)


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    model: ModelVersion
    research_git_commit: str
    dataset_manifest_path: str
    dataset_manifest_version: str
    feature_names: tuple[str, ...]
    feature_code_version: str
    label_config: dict[str, object]
    train_window: TimeWindow
    validation_window: TimeWindow
    test_window: TimeWindow
    cost_assumptions: CostAssumptions
    metrics: dict[str, float | int | str]
    walk_forward_report_path: str
    decision: PromotionDecision
    created_at: datetime

    def to_record_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["created_at"] = _format_timestamp(self.created_at)
        return payload

    @classmethod
    def from_record_dict(cls, payload: dict[str, object]) -> "ExperimentRecord":
        decision = payload["decision"]
        return cls(
            model=ModelVersion(**payload["model"]),
            research_git_commit=str(payload["research_git_commit"]),
            dataset_manifest_path=str(payload["dataset_manifest_path"]),
            dataset_manifest_version=str(payload["dataset_manifest_version"]),
            feature_names=tuple(payload["feature_names"]),
            feature_code_version=str(payload["feature_code_version"]),
            label_config=dict(payload["label_config"]),
            train_window=TimeWindow(**payload["train_window"]),
            validation_window=TimeWindow(**payload["validation_window"]),
            test_window=TimeWindow(**payload["test_window"]),
            cost_assumptions=CostAssumptions(**payload["cost_assumptions"]),
            metrics=dict(payload["metrics"]),
            walk_forward_report_path=str(payload["walk_forward_report_path"]),
            decision=PromotionDecision(
                status=decision["status"],
                reason=str(decision["reason"]),
                gates=tuple(PromotionGateResult(**gate) for gate in decision["gates"]),
                thresholds=dict(decision.get("thresholds", {})),
                reviewed_by=decision.get("reviewed_by"),
                reviewed_at=decision.get("reviewed_at"),
            ),
            created_at=datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00")),
        )


def evaluate_promotion_gates(inputs: PromotionGateInputs) -> PromotionDecision:
    thresholds = inputs.thresholds
    gates = (
        PromotionGateResult(
            name="beats_rule_only_and_naive_oos",
            passed=inputs.model_average_r > inputs.rule_only_average_r
            and inputs.model_average_r > inputs.naive_average_r,
            detail=(
                "model average R must beat rule-only and naive baselines after costs "
                f"({inputs.model_average_r:.4f} vs {inputs.rule_only_average_r:.4f}/"
                f"{inputs.naive_average_r:.4f})"
            ),
        ),
        PromotionGateResult(
            name="walk_forward_metrics_acceptable",
            passed=inputs.walk_forward_average_r >= thresholds.min_walk_forward_average_r,
            detail=(
                "walk-forward average R must meet the configured threshold "
                f"({inputs.walk_forward_average_r:.4f} >= "
                f"{thresholds.min_walk_forward_average_r:.4f})"
            ),
        ),
        PromotionGateResult(
            name="minimum_oos_trade_count",
            passed=inputs.model_oos_trade_count >= thresholds.min_oos_trade_count,
            detail=(
                "model OOS trade count must meet the configured threshold "
                f"({inputs.model_oos_trade_count} >= {thresholds.min_oos_trade_count})"
            ),
        ),
        PromotionGateResult(
            name="drawdown_within_limits",
            passed=inputs.max_drawdown_pct <= thresholds.max_drawdown_pct
            and inputs.max_drawdown_duration_bars <= thresholds.max_drawdown_duration_bars,
            detail=(
                "drawdown must stay within depth/duration limits "
                f"({inputs.max_drawdown_pct:.4%}/{inputs.max_drawdown_duration_bars} bars "
                f"<= {thresholds.max_drawdown_pct:.4%}/"
                f"{thresholds.max_drawdown_duration_bars} bars)"
            ),
        ),
        PromotionGateResult(
            name="feature_leakage_checks_pass",
            passed=inputs.leakage_checks_passed or not thresholds.require_leakage_checks,
            detail="feature leakage checks must pass",
        ),
        PromotionGateResult(
            name="stability_checks_pass",
            passed=inputs.stability_checks_passed or not thresholds.require_stability_checks,
            detail="stability checks must avoid a single fragile parameter optimum",
        ),
        PromotionGateResult(
            name="paper_trading_plan_exists",
            passed=bool(inputs.paper_trading_plan_path.strip())
            or not thresholds.require_paper_trading_plan,
            detail="paper-trading plan path must be attached before promotion",
        ),
    )
    failed_gate_names = [gate.name for gate in gates if not gate.passed]
    if failed_gate_names:
        return PromotionDecision(
            status="reject",
            reason="failed gates: " + ", ".join(failed_gate_names),
            gates=gates,
            thresholds=asdict(thresholds),
        )
    return PromotionDecision(
        status="promote_to_paper_trading",
        reason="all promotion gates passed",
        gates=gates,
        thresholds=asdict(thresholds),
    )


def promotion_checklist_dict(record: ExperimentRecord) -> dict[str, object]:
    return {
        "model_id": record.model.model_id,
        "model_version": record.model.version,
        "model_type": record.model.model_type,
        "status": record.decision.status,
        "reason": record.decision.reason,
        "research_git_commit": record.research_git_commit,
        "dataset_manifest_path": record.dataset_manifest_path,
        "dataset_manifest_version": record.dataset_manifest_version,
        "feature_code_version": record.feature_code_version,
        "feature_names": list(record.feature_names),
        "train_window": asdict(record.train_window),
        "validation_window": asdict(record.validation_window),
        "test_window": asdict(record.test_window),
        "cost_assumptions": asdict(record.cost_assumptions),
        "metrics": record.metrics,
        "thresholds": record.decision.thresholds,
        "gates": [asdict(gate) for gate in record.decision.gates],
        "created_at": _format_timestamp(record.created_at),
    }


def write_promotion_checklist(path: Path, record: ExperimentRecord) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(promotion_checklist_dict(record), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_experiment_record(registry_dir: Path, record: ExperimentRecord) -> Path:
    _validate_record(record)
    record_dir = registry_dir / record.model.model_id / record.model.version
    record_dir.mkdir(parents=True, exist_ok=True)
    path = record_dir / "record.json"
    path.write_text(
        json.dumps(record.to_record_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def list_experiments(registry_dir: Path) -> list[ExperimentRecord]:
    records = [
        ExperimentRecord.from_record_dict(json.loads(path.read_text(encoding="utf-8")))
        for path in registry_dir.glob("*/*/record.json")
    ]
    return sorted(records, key=lambda record: (record.created_at, record.model.model_id))


def format_experiment_list(records: list[ExperimentRecord]) -> str:
    if not records:
        return "No experiments found."

    lines = [
        "| Model | Version | Status | Average R | Walk-forward R | Git commit |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for record in records:
        lines.append(
            "| "
            f"{record.model.model_id} | "
            f"{record.model.version} | "
            f"{record.decision.status.upper()} | "
            f"{float(record.metrics.get('average_r', 0.0)):.4f} | "
            f"{float(record.metrics.get('walk_forward_average_r', 0.0)):.4f} | "
            f"{record.research_git_commit} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crypto Trade research experiment registry.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="List experiment records.")
    list_parser.add_argument("--registry-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "list":
        print(format_experiment_list(list_experiments(args.registry_dir)))


def _validate_record(record: ExperimentRecord) -> None:
    required_values = {
        "model_id": record.model.model_id,
        "model_version": record.model.version,
        "model_type": record.model.model_type,
        "research_git_commit": record.research_git_commit,
        "dataset_manifest_path": record.dataset_manifest_path,
        "dataset_manifest_version": record.dataset_manifest_version,
        "feature_code_version": record.feature_code_version,
        "walk_forward_report_path": record.walk_forward_report_path,
    }
    missing = [name for name, value in required_values.items() if not value.strip()]
    if missing:
        raise ValueError("missing required experiment metadata: " + ", ".join(missing))
    if not record.feature_names:
        raise ValueError("feature_names must not be empty")
    if not record.label_config:
        raise ValueError("label_config must not be empty")
    if not record.metrics:
        raise ValueError("metrics must not be empty")
    if record.cost_assumptions.fee_bps < 0 or record.cost_assumptions.slippage_bps < 0:
        raise ValueError("fee_bps and slippage_bps must be non-negative")
    if record.decision.status not in {"promote_to_paper_trading", "reject"}:
        raise ValueError("decision status must be promote_to_paper_trading or reject")
    if not record.decision.gates:
        raise ValueError("decision gates must not be empty")


def _format_timestamp(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
