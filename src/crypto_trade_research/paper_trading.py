"""Research-only paper-trading pack builder."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_trade_research.models.artifacts import load_model_artifact

PACK_SCHEMA_VERSION = "research.paper-trading-pack.v1"

_FORBIDDEN_LIVE_AUTHORITY_FIELDS = {
    "api_key",
    "api_secret",
    "authorization",
    "credential",
    "credentials",
    "leverage",
    "margin",
    "order_notional",
    "order_quantity",
    "order_size",
    "password",
    "position_size",
    "quantity",
    "secret",
    "token",
}


@dataclass(frozen=True, slots=True)
class PaperSourceArtifacts:
    model_artifact_path: Path
    baseline_report_path: Path
    stability_report_path: Path
    experiment_config_path: Path


@dataclass(frozen=True, slots=True)
class PaperTradingPackConfig:
    pack_name: str
    output_path: Path
    issue_id: str
    epic_id: str
    candidate_name: str
    plan_path: Path
    source_artifacts: PaperSourceArtifacts
    strategy: dict[str, object]
    paper_gate: dict[str, object]
    monitoring: dict[str, object]
    reconciliation: dict[str, object]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaperTradingPackConfig:
        _reject_forbidden_live_authority_fields(payload)
        source = dict(payload["source_artifacts"])
        return cls(
            pack_name=str(payload["pack_name"]),
            output_path=Path(str(payload["output_path"])),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            candidate_name=str(payload["candidate_name"]),
            plan_path=Path(str(payload["plan_path"])),
            source_artifacts=PaperSourceArtifacts(
                model_artifact_path=Path(str(source["model_artifact_path"])),
                baseline_report_path=Path(str(source["baseline_report_path"])),
                stability_report_path=Path(str(source["stability_report_path"])),
                experiment_config_path=Path(str(source["experiment_config_path"])),
            ),
            strategy=dict(payload["strategy"]),
            paper_gate=dict(payload["paper_gate"]),
            monitoring=dict(payload["monitoring"]),
            reconciliation=dict(payload["reconciliation"]),
        )

    @classmethod
    def from_path(cls, path: Path) -> PaperTradingPackConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_paper_trading_pack(config: PaperTradingPackConfig) -> dict[str, object]:
    """Build a self-contained research-only paper-trading pack manifest."""

    model_artifact = load_model_artifact(config.source_artifacts.model_artifact_path)
    baseline_report = _read_json(config.source_artifacts.baseline_report_path)
    stability_report = _read_json(config.source_artifacts.stability_report_path)
    experiment_config = _read_json(config.source_artifacts.experiment_config_path)
    _reject_forbidden_live_authority_fields(
        {
            "strategy": config.strategy,
            "paper_gate": config.paper_gate,
            "monitoring": config.monitoring,
            "reconciliation": config.reconciliation,
            "experiment_config": experiment_config,
        }
    )

    model_metadata = dict(baseline_report.get("model_metadata", {}))
    metadata = dict(baseline_report.get("metadata", {}))
    primary_strategy = str(model_metadata.get("primary_strategy", ""))
    strategies = dict(baseline_report.get("strategies", {}))
    primary_metrics = _strategy_metrics(strategies, primary_strategy)
    source_artifacts = {
        "model_artifact": _artifact_reference(config.source_artifacts.model_artifact_path),
        "baseline_report": _artifact_reference(config.source_artifacts.baseline_report_path),
        "stability_report": _artifact_reference(config.source_artifacts.stability_report_path),
        "experiment_config": _artifact_reference(config.source_artifacts.experiment_config_path),
    }
    payload: dict[str, object] = {
        "schema_version": PACK_SCHEMA_VERSION,
        "pack_name": config.pack_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "candidate_name": config.candidate_name,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "research_git_commit": _git_commit(),
        "plan_path": str(config.plan_path),
        "source_artifacts": source_artifacts,
        "candidate": {
            "model_id": model_artifact.model_id,
            "model_version": model_artifact.model_version,
            "model_type": model_artifact.model.model_type,
            "artifact_hash": model_artifact.artifact_hash,
            "feature_set_version": model_artifact.feature_schema.feature_set_version,
            "feature_count": len(model_artifact.feature_schema.feature_names),
            "dataset_manifest_path": model_artifact.dataset_manifest_path,
            "funding_manifest_path": metadata.get("funding_manifest_path", ""),
            "calibration": model_artifact.calibration,
            "primary_strategy": primary_strategy,
            "training_target": model_metadata.get("training_target", ""),
            "risk_controls": model_metadata.get("risk_controls", {}),
        },
        "strategy": config.strategy,
        "research_evidence": {
            "oos_average_r": _float(primary_metrics.get("average_r")),
            "oos_trade_count": _int(primary_metrics.get("trade_count")),
            "oos_max_drawdown_pct": _float(primary_metrics.get("max_drawdown_pct")),
            "oos_profit_factor": _float(primary_metrics.get("profit_factor")),
            "rule_only_average_r": _float(
                _strategy_metrics(strategies, "rule_only_oos").get("average_r")
            ),
            "stability_status": dict(stability_report.get("stability_report", {})).get(
                "status", "unknown"
            ),
        },
        "paper_gate": config.paper_gate,
        "monitoring": config.monitoring,
        "reconciliation": config.reconciliation,
        "safety": {
            "live_order_authority": False,
            "allowed_actions": ["log_signal", "paper_fill", "paper_skip"],
            "forbidden_actions": [
                "place_live_order",
                "cancel_live_order",
                "change_leverage",
                "change_margin",
                "write_runtime_trade_state",
            ],
            "secret_free_logging_required": True,
        },
        "decision": {
            "status": "paper_dry_run_pack_ready",
            "paper_trading_approved": True,
            "live_trading_approved": False,
            "working_model": False,
            "notes": (
                "Research candidate may enter fake-executor or paper-ledger dry run only. "
                "CT-113 remains open until paper evidence passes the gate."
            ),
        },
    }
    _reject_forbidden_live_authority_fields(payload)
    _write_json(config.output_path, payload)
    return payload


def _artifact_reference(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(path)
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(path)
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _strategy_metrics(strategies: dict[str, object], strategy_name: str) -> dict[str, object]:
    strategy = dict(strategies.get(strategy_name, {}))
    return dict(strategy.get("metrics", strategy))


def _reject_forbidden_live_authority_fields(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_LIVE_AUTHORITY_FIELDS:
                raise ValueError(f"forbidden live authority field at {path}.{key}")
            _reject_forbidden_live_authority_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_live_authority_fields(item, f"{path}[{index}]")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    config = PaperTradingPackConfig.from_path(args.config)
    payload = build_paper_trading_pack(config)
    print(json.dumps({"output_path": str(config.output_path), "status": payload["decision"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
