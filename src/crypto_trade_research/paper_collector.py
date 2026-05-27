"""Research-only forward paper signal and ledger collector."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.models.artifacts import ModelArtifact, load_model_artifact

COLLECTOR_SCHEMA_VERSION = "research.paper-signal-ledger.v1"
CONTRACT_VERSION = "ml-inference.v1"


@dataclass(frozen=True, slots=True)
class PaperCollectorConfig:
    run_name: str
    output_dir: Path
    issue_id: str
    epic_id: str
    pack_manifest_path: Path
    feature_source_path: Path
    label_source_path: Path | None
    decision_time: str | None
    mode: Literal["historical_dry_run", "forward_paper"]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PaperCollectorConfig:
        label_source_path = payload.get("label_source_path")
        return cls(
            run_name=str(payload["run_name"]),
            output_dir=Path(str(payload["output_dir"])),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            pack_manifest_path=Path(str(payload["pack_manifest_path"])),
            feature_source_path=Path(str(payload["feature_source_path"])),
            label_source_path=Path(str(label_source_path)) if label_source_path else None,
            decision_time=(
                str(payload["decision_time"]) if payload.get("decision_time") is not None else None
            ),
            mode=_mode(str(payload["mode"])),
        )

    @classmethod
    def from_path(cls, path: Path) -> PaperCollectorConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def run_paper_collector(config: PaperCollectorConfig) -> dict[str, object]:
    """Generate research-only paper signals and ledger entries."""

    pack = _read_json(config.pack_manifest_path)
    artifact = _load_pack_model_artifact(pack)
    if artifact.expected_r_model is None:
        raise ValueError("paper collector requires expected_r_model in model artifact")

    features = _read_rows(config.feature_source_path)
    labels = _label_map(_read_rows(config.label_source_path)) if config.label_source_path else {}
    candidate_rows = _candidate_rows(features, pack)
    scored_rows = _score_rows(candidate_rows, artifact, pack)
    selected_time = config.decision_time or _latest_decision_time_with_takes(scored_rows)
    selected_rows = [row for row in scored_rows if row["decision_time"] == selected_time]
    signals = _signals(selected_rows, artifact, pack, config)
    ledger = _ledger_entries(signals, labels, pack, config)
    summary = {
        "candidate_count": len(selected_rows),
        "signal_count": len(signals),
        "take_count": sum(1 for signal in signals if signal["recommended_action"] == "take"),
        "ledger_entry_count": len(ledger),
        "decision_time": selected_time,
        "mode": config.mode,
    }
    payload: dict[str, object] = {
        "schema_version": COLLECTOR_SCHEMA_VERSION,
        "run_name": config.run_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "mode": config.mode,
        "pack_manifest_path": str(config.pack_manifest_path),
        "feature_source_path": str(config.feature_source_path),
        "label_source_path": str(config.label_source_path) if config.label_source_path else "",
        "candidate_name": pack.get("candidate_name", ""),
        "model": {
            "model_id": artifact.model_id,
            "model_version": artifact.model_version,
            "artifact_hash": artifact.artifact_hash,
            "expected_r_model_available": True,
        },
        "summary": summary,
        "signals": signals,
        "trades": ledger,
        "safety": {
            "live_order_authority": False,
            "allowed_actions": ["log_signal", "paper_fill", "paper_skip"],
            "live_trading_approved": False,
        },
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(config.output_dir / "signals.json", payload)
    _write_json(config.output_dir / "ledger.json", {"trades": ledger, "metrics": {}})
    return payload


def _load_pack_model_artifact(pack: dict[str, object]) -> ModelArtifact:
    source_artifacts = dict(pack["source_artifacts"])
    model_ref = dict(source_artifacts["model_artifact"])
    return load_model_artifact(Path(str(model_ref["path"])))


def _read_rows(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return []
    if path.suffix == ".parquet":
        return [dict(row) for row in pq.read_table(path).to_pylist()]
    return [dict(row) for row in json.loads(path.read_text(encoding="utf-8"))]


def _candidate_rows(
    rows: list[dict[str, object]], pack: dict[str, object]
) -> list[dict[str, object]]:
    strategy = dict(pack["strategy"])
    filters = [dict(item) for item in strategy.get("filters", ())]
    symbols = {str(symbol) for symbol in strategy.get("symbols", ())}
    return [
        row
        for row in rows
        if str(row.get("symbol")) in symbols and all(_filter_passes(row, item) for item in filters)
    ]


def _filter_passes(row: dict[str, object], item: dict[str, object]) -> bool:
    raw_value = row.get(str(item["feature"]))
    if raw_value is None:
        return False
    value = float(raw_value)
    threshold = float(item["value"])
    operator = str(item["operator"])
    if operator == "<=":
        return value <= threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == ">":
        return value > threshold
    raise ValueError(f"unsupported filter operator: {operator}")


def _score_rows(
    rows: list[dict[str, object]],
    artifact: ModelArtifact,
    pack: dict[str, object],
) -> list[dict[str, object]]:
    feature_names = artifact.feature_schema.feature_names
    threshold = _expected_r_threshold(pack, artifact)
    top_n = _top_n(pack)
    by_time: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        feature_values = {
            name: float(row[name])
            for name in feature_names
            if name in row and row[name] is not None
        }
        prediction = artifact.predict(feature_values)
        if prediction.expected_r is None:
            continue
        scored = dict(row)
        scored["decision_time"] = _timestamp_text(row["decision_time"])
        if scored.get("source_available_at") is not None:
            scored["source_available_at"] = _timestamp_text(scored["source_available_at"])
        scored["expected_r"] = prediction.expected_r
        scored["target_before_stop_probability"] = prediction.target_before_stop_probability
        scored["expected_r_threshold_passed"] = prediction.expected_r >= threshold
        by_time[str(scored["decision_time"])].append(scored)

    ranked: list[dict[str, object]] = []
    for _, group in by_time.items():
        ordered = sorted(group, key=lambda row: float(row["expected_r"]), reverse=True)
        for index, row in enumerate(ordered, start=1):
            row["rank"] = index
            row["top_n_passed"] = index <= top_n
            row["paper_take"] = bool(row["expected_r_threshold_passed"]) and index <= top_n
            ranked.append(row)
    return ranked


def _latest_decision_time_with_takes(rows: list[dict[str, object]]) -> str:
    times = sorted({str(row["decision_time"]) for row in rows if row.get("paper_take")})
    if not times:
        raise ValueError("no paper-take candidates available")
    return times[-1]


def _signals(
    rows: list[dict[str, object]],
    artifact: ModelArtifact,
    pack: dict[str, object],
    config: PaperCollectorConfig,
) -> list[dict[str, object]]:
    generated_at = _format_timestamp(datetime.now(UTC))
    signals = []
    for row in sorted(rows, key=lambda item: int(item["rank"])):
        signal_timestamp = str(row["decision_time"])
        features_timestamp = str(row.get("source_available_at") or row["decision_time"])
        hard_blocks = [] if row["paper_take"] else ["expected_r_or_rank_block"]
        reason_codes = _reason_codes(row)
        signals.append(
            {
                "contract_version": CONTRACT_VERSION,
                "request_id": f"{config.run_name}:{signal_timestamp}:{row['symbol']}",
                "model_id": artifact.model_id,
                "model_version": artifact.model_version,
                "artifact_hash": artifact.artifact_hash,
                "symbol": str(row["symbol"]),
                "timeframe": str(row["timeframe"]),
                "signal_timestamp": signal_timestamp,
                "features_timestamp": features_timestamp,
                "data_freshness_seconds": _seconds_between(features_timestamp, signal_timestamp),
                "feature_freshness_seconds": _seconds_between(features_timestamp, signal_timestamp),
                "funding_source_latency_seconds": _funding_latency_seconds(row),
                "regime": {
                    "label": _regime_label(row),
                    "probabilities": {"unknown": 1.0},
                },
                "expected_r": float(row["expected_r"]),
                "target_before_stop_probability": float(row["target_before_stop_probability"]),
                "confidence": max(0.01, min(1.0, float(row["expected_r"]))),
                "rank": int(row["rank"]),
                "top_n": _top_n(pack),
                "entry_price": _optional_float(row.get("entry_price")),
                "stop_price": _stop_price(row, pack),
                "target_price": _target_price(row, pack),
                "recommended_action": "take" if row["paper_take"] else "skip",
                "reason_codes": reason_codes,
                "hard_risk_blocks": hard_blocks,
                "generated_at": generated_at,
            }
        )
    return signals


def _reason_codes(row: dict[str, object]) -> list[str]:
    if row["paper_take"]:
        return ["expected_r_above_threshold", "rank_within_top_n"]
    reasons = []
    if not row["expected_r_threshold_passed"]:
        reasons.append("expected_r_below_threshold")
    if not row["top_n_passed"]:
        reasons.append("outside_top_n")
    return reasons or ["paper_skip"]


def _ledger_entries(
    signals: list[dict[str, object]],
    labels: dict[tuple[str, str], dict[str, object]],
    pack: dict[str, object],
    config: PaperCollectorConfig,
) -> list[dict[str, object]]:
    entries = []
    for signal in signals:
        if signal["recommended_action"] != "take":
            continue
        key = (str(signal["symbol"]), str(signal["signal_timestamp"]))
        label = labels.get(key)
        entry = {
            "decision_time": signal["signal_timestamp"],
            "symbol": signal["symbol"],
            "timeframe": signal["timeframe"],
            "side": str(dict(pack["strategy"]).get("side", "long")),
            "strategy_name": config.run_name,
            "model_id": signal["model_id"],
            "model_version": signal["model_version"],
            "artifact_hash": signal["artifact_hash"],
            "expected_r": signal["expected_r"],
            "target_before_stop_probability": signal["target_before_stop_probability"],
            "rank": signal["rank"],
            "feature_freshness_seconds": signal["feature_freshness_seconds"],
            "funding_source_latency_seconds": signal["funding_source_latency_seconds"],
            "entry_price": signal.get("entry_price"),
            "stop_price": signal.get("stop_price"),
            "target_price": signal.get("target_price"),
            "paper_status": "open",
            "live_order_authority": False,
        }
        if label is not None:
            entry.update(
                {
                    "paper_status": "closed",
                    "net_r": float(label["realized_r_after_costs"]),
                    "gross_r": float(label["realized_r_after_costs"]),
                    "exit_reason": _label_exit_reason(label),
                    "entry_price": float(label["entry_price"]),
                    "stop_price": float(label["stop_price"]),
                    "target_price": float(label["target_price"]),
                }
            )
        entries.append(entry)
    return entries


def _label_map(rows: list[dict[str, object]]) -> dict[tuple[str, str], dict[str, object]]:
    return {(str(row["symbol"]), _timestamp_text(row["decision_time"])): row for row in rows}


def _label_exit_reason(label: dict[str, object]) -> str:
    if bool(label.get("target_before_stop")):
        return "target"
    if label.get("dynamic_exit_reason"):
        return str(label["dynamic_exit_reason"])
    return "stop_or_timeout"


def _expected_r_threshold(pack: dict[str, object], artifact: ModelArtifact) -> float:
    strategy = dict(pack["strategy"])
    ranking = dict(strategy.get("ranking", {}))
    if ranking.get("selected_expected_r_threshold") is not None:
        return float(ranking["selected_expected_r_threshold"])
    assert artifact.expected_r_model is not None
    return artifact.expected_r_model.expected_r_threshold


def _top_n(pack: dict[str, object]) -> int:
    strategy = dict(pack["strategy"])
    ranking = dict(strategy.get("ranking", {}))
    return int(ranking.get("top_n_per_decision_time", 1))


def _stop_price(row: dict[str, object], pack: dict[str, object]) -> float | None:
    entry_price = _optional_float(row.get("entry_price"))
    if entry_price is None:
        return None
    strategy = dict(pack["strategy"])
    exits = dict(strategy.get("exits", {}))
    stop_loss_pct = float(exits.get("stop_loss_pct", 0.0))
    if str(strategy.get("side", "long")) == "short":
        return entry_price * (1 + stop_loss_pct)
    return entry_price * (1 - stop_loss_pct)


def _target_price(row: dict[str, object], pack: dict[str, object]) -> float | None:
    entry_price = _optional_float(row.get("entry_price"))
    if entry_price is None:
        return None
    strategy = dict(pack["strategy"])
    exits = dict(strategy.get("exits", {}))
    target_pct = float(exits.get("target_pct", 0.0))
    if str(strategy.get("side", "long")) == "short":
        return entry_price * (1 - target_pct)
    return entry_price * (1 + target_pct)


def _regime_label(row: dict[str, object]) -> str:
    risk_score = float(row.get("risk_on_score_20", 0.0))
    if risk_score > 0.55:
        return "risk_on"
    if risk_score < 0.45:
        return "risk_off"
    return "mixed"


def _funding_latency_seconds(row: dict[str, object]) -> float:
    if row.get("hours_since_funding") is None:
        return 0.0
    return float(row["hours_since_funding"]) * 3600


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _seconds_between(start: str, end: str) -> float:
    return (_parse_timestamp(end) - _parse_timestamp(start)).total_seconds()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp_text(value: object) -> str:
    if isinstance(value, datetime):
        return _format_timestamp(value)
    return str(value)


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_rows_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _mode(value: str) -> Literal["historical_dry_run", "forward_paper"]:
    if value in {"historical_dry_run", "forward_paper"}:
        return value  # type: ignore[return-value]
    raise ValueError("mode must be historical_dry_run or forward_paper")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    config = PaperCollectorConfig.from_path(args.config)
    payload = run_paper_collector(config)
    print(json.dumps({"output_dir": str(config.output_dir), "summary": payload["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
