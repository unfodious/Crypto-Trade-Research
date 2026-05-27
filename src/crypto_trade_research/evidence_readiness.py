"""CT-113 forward evidence readiness report."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.ct113_forward_evidence_readiness.v1"


class EvidenceReadinessError(ValueError):
    """Raised when the evidence readiness report cannot be built."""


@dataclass(frozen=True, slots=True)
class ForwardPaperStreamConfig:
    name: str
    issue_id: str
    forward_run_path: Path
    monitoring_report_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ForwardPaperStreamConfig:
        return cls(
            name=str(payload["name"]),
            issue_id=str(payload["issue_id"]),
            forward_run_path=Path(str(payload["forward_run_path"])),
            monitoring_report_path=Path(str(payload["monitoring_report_path"])),
        )


@dataclass(frozen=True, slots=True)
class EvidenceReadinessConfig:
    report_name: str
    issue_id: str
    epic_id: str
    output_json_path: Path
    output_markdown_path: Path
    external_features_run_path: Path
    forward_paper_streams: tuple[ForwardPaperStreamConfig, ...]
    minimum_external_feature_rows: int = 500
    minimum_crowding_snapshots: int = 1
    minimum_order_book_snapshots: int = 1
    minimum_liquidation_snapshots: int = 1
    minimum_forward_signals: int = 30
    minimum_closed_trades: int = 30
    minimum_calendar_days: int = 7

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidenceReadinessConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            external_features_run_path=Path(str(payload["external_features_run_path"])),
            forward_paper_streams=tuple(
                ForwardPaperStreamConfig.from_dict(dict(stream))
                for stream in payload["forward_paper_streams"]
            ),
            minimum_external_feature_rows=int(payload.get("minimum_external_feature_rows", 500)),
            minimum_crowding_snapshots=int(payload.get("minimum_crowding_snapshots", 1)),
            minimum_order_book_snapshots=int(payload.get("minimum_order_book_snapshots", 1)),
            minimum_liquidation_snapshots=int(payload.get("minimum_liquidation_snapshots", 1)),
            minimum_forward_signals=int(payload.get("minimum_forward_signals", 30)),
            minimum_closed_trades=int(payload.get("minimum_closed_trades", 30)),
            minimum_calendar_days=int(payload.get("minimum_calendar_days", 7)),
        )

    @classmethod
    def from_path(cls, path: Path) -> EvidenceReadinessConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_evidence_readiness_report(config: EvidenceReadinessConfig) -> dict[str, object]:
    """Build a conservative readiness report before external-feature validation."""

    _validate_config(config)
    external = _read_json(config.external_features_run_path)
    streams = [_stream_summary(stream) for stream in config.forward_paper_streams]
    aggregate = _aggregate_streams(streams)
    gates = _gates(config, external, aggregate)
    validation_ready = all(bool(gate["passed"]) for gate in gates)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "external_features": _external_summary(external, config.external_features_run_path),
        "forward_paper_streams": streams,
        "aggregate_forward_paper": aggregate,
        "gates": gates,
        "readiness_status": "ready_for_validation" if validation_ready else "not_ready",
        "decision": {
            "ready_for_external_validation_matrix": validation_ready,
            "working_model": False,
            "live_trading_approved": False,
        },
        "notes": (
            "Research-only readiness report. Backtests and forward paper are evidence, not live "
            "trading approval."
        ),
    }
    _write_report(config, payload)
    return payload


def _external_summary(
    external: dict[str, object],
    path: Path,
) -> dict[str, object]:
    return {
        "run_path": str(path),
        "latest_generated_at": _text(external.get("latest_generated_at")),
        "row_count": _int(external.get("row_count")),
        "crowding_snapshot_count": _int(external.get("crowding_snapshot_count")),
        "order_book_snapshot_count": _int(external.get("order_book_snapshot_count")),
        "liquidation_snapshot_count": _int(external.get("liquidation_snapshot_count")),
        "symbol_count": len(_list(external.get("symbols"))),
        "warnings": _list(external.get("warnings")),
    }


def _stream_summary(config: ForwardPaperStreamConfig) -> dict[str, object]:
    forward_run = _read_json(config.forward_run_path)
    monitoring = _read_json(config.monitoring_report_path)
    collector = _dict(forward_run.get("collector_summary"))
    row_counts = _dict(forward_run.get("row_counts"))
    metrics = _dict(monitoring.get("metrics"))
    return {
        "name": config.name,
        "issue_id": config.issue_id,
        "forward_run_path": str(config.forward_run_path),
        "monitoring_report_path": str(config.monitoring_report_path),
        "latest_decision_time": _text(collector.get("decision_time")),
        "candidate_count": _int(collector.get("candidate_count")),
        "signal_count": _int(collector.get("signal_count")),
        "take_count": _int(collector.get("take_count")),
        "cumulative_signals": _int(row_counts.get("cumulative_signals")),
        "cumulative_trades": _int(row_counts.get("cumulative_trades")),
        "closed_trades": _int(row_counts.get("closed_trades")),
        "open_trades": _int(row_counts.get("open_trades")),
        "monitoring_status": _text(monitoring.get("monitoring_status")),
        "calendar_days": _int(metrics.get("calendar_days")),
        "trade_count": _int(metrics.get("trade_count")),
        "average_r_after_costs": _float(metrics.get("average_r_after_costs")),
        "max_drawdown_pct": _float(metrics.get("max_drawdown_pct")),
        "warnings": _list(monitoring.get("warnings")),
        "working_model": bool(_dict(monitoring.get("decision")).get("working_model", False)),
        "live_trading_approved": bool(
            _dict(monitoring.get("decision")).get("live_trading_approved", False)
        ),
    }


def _aggregate_streams(streams: list[dict[str, object]]) -> dict[str, object]:
    latest_decision_time = max(
        (_text(stream.get("latest_decision_time")) for stream in streams),
        default="",
    )
    return {
        "stream_count": len(streams),
        "calendar_days": max((_int(stream.get("calendar_days")) for stream in streams), default=0),
        "latest_decision_time": latest_decision_time,
        "total_cumulative_signals": sum(
            _int(stream.get("cumulative_signals")) for stream in streams
        ),
        "total_cumulative_trades": sum(_int(stream.get("cumulative_trades")) for stream in streams),
        "total_closed_trades": sum(_int(stream.get("closed_trades")) for stream in streams),
        "total_monitoring_trade_count": sum(_int(stream.get("trade_count")) for stream in streams),
        "any_live_trading_approved": any(
            bool(stream.get("live_trading_approved")) for stream in streams
        ),
        "any_working_model_claim": any(bool(stream.get("working_model")) for stream in streams),
    }


def _gates(
    config: EvidenceReadinessConfig,
    external: dict[str, object],
    aggregate: dict[str, object],
) -> list[dict[str, object]]:
    external_summary = _external_summary(external, config.external_features_run_path)
    return [
        _gate(
            "external_feature_rows",
            _int(external_summary["row_count"]) >= config.minimum_external_feature_rows,
            f"{external_summary['row_count']} rows >= {config.minimum_external_feature_rows}",
        ),
        _gate(
            "crowding_snapshots",
            _int(external_summary["crowding_snapshot_count"]) >= config.minimum_crowding_snapshots,
            f"{external_summary['crowding_snapshot_count']} snapshots",
        ),
        _gate(
            "order_book_snapshots",
            _int(external_summary["order_book_snapshot_count"])
            >= config.minimum_order_book_snapshots,
            f"{external_summary['order_book_snapshot_count']} snapshots",
        ),
        _gate(
            "liquidation_snapshots",
            _int(external_summary["liquidation_snapshot_count"])
            >= config.minimum_liquidation_snapshots,
            f"{external_summary['liquidation_snapshot_count']} snapshots",
        ),
        _gate(
            "minimum_forward_signals",
            _int(aggregate["total_cumulative_signals"]) >= config.minimum_forward_signals,
            f"{aggregate['total_cumulative_signals']} signals >= {config.minimum_forward_signals}",
        ),
        _gate(
            "minimum_closed_trades",
            _int(aggregate["total_closed_trades"]) >= config.minimum_closed_trades,
            f"{aggregate['total_closed_trades']} trades >= {config.minimum_closed_trades}",
        ),
        _gate(
            "minimum_calendar_days",
            _int(aggregate["calendar_days"]) >= config.minimum_calendar_days,
            f"{aggregate['calendar_days']} days >= {config.minimum_calendar_days}",
        ),
        _gate(
            "no_working_model_claim",
            not bool(aggregate["any_working_model_claim"]),
            str(aggregate["any_working_model_claim"]),
        ),
        _gate(
            "no_live_trading_approval",
            not bool(aggregate["any_live_trading_approved"]),
            str(aggregate["any_live_trading_approved"]),
        ),
    ]


def _gate(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": passed, "detail": detail}


def _write_report(config: EvidenceReadinessConfig, payload: dict[str, object]) -> None:
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")


def _markdown_report(payload: dict[str, object]) -> str:
    external = _dict(payload["external_features"])
    aggregate = _dict(payload["aggregate_forward_paper"])
    gates = [_dict(gate) for gate in _list(payload["gates"])]
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        f"Readiness status: `{payload['readiness_status']}`",
        "",
        "## External Features",
        "",
        f"- rows: `{external['row_count']}`",
        f"- crowding snapshots: `{external['crowding_snapshot_count']}`",
        f"- order-book snapshots: `{external['order_book_snapshot_count']}`",
        f"- liquidation snapshots: `{external['liquidation_snapshot_count']}`",
        f"- warnings: `{len(_list(external.get('warnings')))}`",
        "",
        "## Forward Paper",
        "",
        f"- streams: `{aggregate['stream_count']}`",
        f"- calendar days: `{aggregate['calendar_days']}`",
        f"- cumulative signals: `{aggregate['total_cumulative_signals']}`",
        f"- closed trades: `{aggregate['total_closed_trades']}`",
        f"- working model claim: `{aggregate['any_working_model_claim']}`",
        f"- live trading approved: `{aggregate['any_live_trading_approved']}`",
        "",
        "## Gates",
        "",
    ]
    for gate in gates:
        status = "pass" if gate["passed"] else "fail"
        lines.append(f"- `{gate['name']}`: `{status}` ({gate['detail']})")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "This is a research-only readiness report. It does not promote a working model and "
            "does not approve live trading.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_config(config: EvidenceReadinessConfig) -> None:
    if not config.forward_paper_streams:
        raise EvidenceReadinessError("forward_paper_streams must not be empty")
    if config.minimum_external_feature_rows <= 0:
        raise EvidenceReadinessError("minimum_external_feature_rows must be positive")
    if config.minimum_forward_signals < 0 or config.minimum_closed_trades < 0:
        raise EvidenceReadinessError("minimum forward evidence gates must be non-negative")


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise EvidenceReadinessError(f"missing input file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidenceReadinessError(f"input JSON must be an object: {path}")
    return payload


def _dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _int(value: object) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def _float(value: object) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = build_evidence_readiness_report(EvidenceReadinessConfig.from_path(args.config))
    print(report["readiness_status"])


if __name__ == "__main__":
    main()
