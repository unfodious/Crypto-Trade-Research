"""Research-only paper ledger monitoring for candidate dry runs."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from crypto_trade_research.models.artifacts import load_model_artifact

MONITORING_SCHEMA_VERSION = "research.paper-monitoring-report.v1"


@dataclass(frozen=True, slots=True)
class PaperMonitoringConfig:
    report_name: str
    output_path: Path
    issue_id: str
    epic_id: str
    pack_manifest_path: Path
    ledger_source_path: Path
    ledger_strategy_name: str
    evidence_type: Literal["historical_replay_seed", "forward_paper"]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaperMonitoringConfig:
        return cls(
            report_name=str(payload["report_name"]),
            output_path=Path(str(payload["output_path"])),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            pack_manifest_path=Path(str(payload["pack_manifest_path"])),
            ledger_source_path=Path(str(payload["ledger_source_path"])),
            ledger_strategy_name=str(payload["ledger_strategy_name"]),
            evidence_type=_evidence_type(str(payload["evidence_type"])),
        )

    @classmethod
    def from_path(cls, path: Path) -> PaperMonitoringConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_paper_monitoring_report(config: PaperMonitoringConfig) -> dict[str, object]:
    """Build a paper monitoring report from a pack manifest and ledger-like trades."""

    pack = _read_json(config.pack_manifest_path)
    ledger = _read_json(config.ledger_source_path)
    trades, source_metrics = _ledger_trades(ledger, config.ledger_strategy_name)
    gate = dict(pack.get("paper_gate", {}))
    metrics = _paper_metrics(trades, source_metrics)
    gate_results = _gate_results(metrics, gate, config.evidence_type)
    model_artifact_status = _model_artifact_status(pack)
    warnings = _warnings(trades, config.evidence_type, model_artifact_status)
    payload: dict[str, object] = {
        "schema_version": MONITORING_SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "evidence_type": config.evidence_type,
        "candidate_name": pack.get("candidate_name", ""),
        "pack_manifest_path": str(config.pack_manifest_path),
        "ledger_source_path": str(config.ledger_source_path),
        "ledger_strategy_name": config.ledger_strategy_name,
        "metrics": metrics,
        "gate_results": gate_results,
        "monitoring_status": _monitoring_status(gate_results, warnings),
        "model_artifact_status": model_artifact_status,
        "warnings": warnings,
        "decision": {
            "forward_paper_gate_passed": (
                config.evidence_type == "forward_paper"
                and all(bool(gate["passed"]) for gate in gate_results)
                and not warnings
            ),
            "live_trading_approved": False,
            "working_model": False,
        },
    }
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _ledger_trades(
    ledger: dict[str, object],
    strategy_name: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if "strategies" in ledger:
        strategy = dict(dict(ledger["strategies"])[strategy_name])
        return [dict(trade) for trade in strategy.get("trades", ())], dict(
            strategy.get("metrics", {})
        )
    return [dict(trade) for trade in ledger.get("trades", ())], dict(ledger.get("metrics", {}))


def _paper_metrics(
    trades: list[dict[str, object]],
    source_metrics: dict[str, object],
) -> dict[str, object]:
    net_r_values = [_float(trade.get("net_r")) for trade in trades]
    positive = [value for value in net_r_values if value > 0]
    negative = [value for value in net_r_values if value < 0]
    days = sorted(
        {_parse_timestamp(str(trade["decision_time"])).date().isoformat() for trade in trades}
    )
    return {
        "calendar_days": _calendar_days(days),
        "trade_count": len(trades),
        "average_r_after_costs": _mean(net_r_values),
        "profit_factor": sum(positive) / abs(sum(negative)) if negative else float("inf"),
        "max_drawdown_pct": _metric_or_computed_drawdown(source_metrics, net_r_values),
        "max_drawdown_duration": _int(source_metrics.get("max_drawdown_duration"))
        if source_metrics
        else None,
        "single_day_positive_r_share": _top_positive_day_share(trades),
        "positive_symbol_breadth": _positive_group_fraction(trades, "symbol"),
        "positive_session_breadth": _positive_session_fraction(trades),
        "rejection_reasons": dict(
            Counter(
                str(trade.get("rejection_reason", ""))
                for trade in trades
                if trade.get("rejection_reason")
            )
        ),
        "missing_feature_freshness_count": sum(
            1 for trade in trades if "feature_freshness_seconds" not in trade
        ),
        "missing_funding_latency_count": sum(
            1 for trade in trades if "funding_source_latency_seconds" not in trade
        ),
    }


def _gate_results(
    metrics: dict[str, object],
    gate: dict[str, object],
    evidence_type: str,
) -> list[dict[str, object]]:
    return [
        _gate("forward_paper_evidence", evidence_type == "forward_paper", evidence_type),
        _gate(
            "minimum_calendar_days",
            _float(metrics["calendar_days"]) >= _float(gate.get("minimum_calendar_days", 30)),
            f"{metrics['calendar_days']} days",
        ),
        _gate(
            "minimum_paper_trades",
            _int(metrics["trade_count"]) >= _int(gate.get("minimum_paper_trades", 100)),
            f"{metrics['trade_count']} trades",
        ),
        _gate(
            "positive_average_r",
            _float(metrics["average_r_after_costs"])
            > _float(gate.get("minimum_average_r_after_costs", 0.0)),
            f"{_float(metrics['average_r_after_costs']):.4f} avg R",
        ),
        _gate(
            "drawdown_within_limit",
            _float(metrics["max_drawdown_pct"])
            <= _float(gate.get("maximum_simulated_drawdown_pct", 0.08)),
            f"{_float(metrics['max_drawdown_pct']):.2%} DD",
        ),
        _gate(
            "single_day_concentration",
            _float(metrics["single_day_positive_r_share"])
            <= _float(gate.get("maximum_single_day_positive_r_share", 0.75)),
            f"{_float(metrics['single_day_positive_r_share']):.2%} top day share",
        ),
        _gate(
            "symbol_breadth",
            _float(metrics["positive_symbol_breadth"])
            >= _float(gate.get("minimum_positive_symbol_breadth", 0.5)),
            f"{_float(metrics['positive_symbol_breadth']):.2%} positive symbols",
        ),
        _gate(
            "session_breadth",
            _float(metrics["positive_session_breadth"])
            >= _float(gate.get("minimum_positive_session_breadth", 0.5)),
            f"{_float(metrics['positive_session_breadth']):.2%} positive sessions",
        ),
    ]


def _model_artifact_status(pack: dict[str, object]) -> dict[str, object]:
    source_artifacts = dict(pack.get("source_artifacts", {}))
    model_ref = dict(source_artifacts.get("model_artifact", {}))
    path = Path(str(model_ref.get("path", "")))
    if not path.exists():
        return {
            "available": False,
            "expected_r_model_available": False,
            "error": "missing artifact",
        }
    artifact = load_model_artifact(path)
    return {
        "available": True,
        "model_id": artifact.model_id,
        "model_version": artifact.model_version,
        "expected_r_model_available": artifact.expected_r_model is not None,
        "error": "",
    }


def _warnings(
    trades: list[dict[str, object]],
    evidence_type: str,
    model_artifact_status: dict[str, object],
) -> list[str]:
    warnings: list[str] = []
    if evidence_type != "forward_paper":
        warnings.append("report is a historical replay seed, not forward paper evidence")
    if not bool(model_artifact_status.get("expected_r_model_available", False)):
        warnings.append("expected-R model is not available in the model artifact")
    if any("feature_freshness_seconds" not in trade for trade in trades):
        warnings.append("ledger is missing feature freshness fields")
    if any("funding_source_latency_seconds" not in trade for trade in trades):
        warnings.append("ledger is missing funding latency fields")
    return warnings


def _monitoring_status(gates: list[dict[str, object]], warnings: list[str]) -> str:
    if any(not bool(gate["passed"]) for gate in gates):
        return "gate_failed"
    if warnings:
        return "warning"
    return "pass"


def _gate(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"name": name, "passed": passed, "detail": detail}


def _metric_or_computed_drawdown(
    source_metrics: dict[str, object], net_r_values: list[float]
) -> float:
    if source_metrics.get("max_drawdown_pct") is not None:
        return _float(source_metrics["max_drawdown_pct"])
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for net_r in net_r_values:
        equity *= 1 + net_r * 0.01
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return max_drawdown


def _positive_group_fraction(trades: list[dict[str, object]], key: str) -> float:
    groups: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        groups[str(trade[key])].append(_float(trade.get("net_r")))
    if not groups:
        return 0.0
    positive = [values for values in groups.values() if _mean(values) > 0]
    return len(positive) / len(groups)


def _positive_session_fraction(trades: list[dict[str, object]]) -> float:
    groups: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        groups[_session(_parse_timestamp(str(trade["decision_time"])))].append(
            _float(trade.get("net_r"))
        )
    if not groups:
        return 0.0
    positive = [values for values in groups.values() if _mean(values) > 0]
    return len(positive) / len(groups)


def _top_positive_day_share(trades: list[dict[str, object]]) -> float:
    groups: dict[str, float] = defaultdict(float)
    for trade in trades:
        day = _parse_timestamp(str(trade["decision_time"])).date().isoformat()
        groups[day] += max(0.0, _float(trade.get("net_r")))
    total = sum(groups.values())
    return max(groups.values()) / total if total > 0 else 0.0


def _calendar_days(days: list[str]) -> int:
    if not days:
        return 0
    start = datetime.fromisoformat(days[0])
    end = datetime.fromisoformat(days[-1])
    return (end - start).days + 1


def _session(value: datetime) -> str:
    if value.hour < 8:
        return "Asia"
    if value.hour < 16:
        return "Europe"
    return "US"


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _float(value: object) -> float:
    return float(value if value is not None else 0.0)


def _int(value: object) -> int:
    return int(value if value is not None else 0)


def _evidence_type(value: str) -> Literal["historical_replay_seed", "forward_paper"]:
    if value in {"historical_replay_seed", "forward_paper"}:
        return value  # type: ignore[return-value]
    raise ValueError("evidence_type must be historical_replay_seed or forward_paper")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    config = PaperMonitoringConfig.from_path(args.config)
    payload = build_paper_monitoring_report(config)
    print(
        json.dumps({"output_path": str(config.output_path), "status": payload["monitoring_status"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
