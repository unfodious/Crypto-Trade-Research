"""Diagnose why forward-paper pack filters do or do not emit candidates."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

SCHEMA_VERSION = "research.forward_filter_diagnostics.v1"


class ForwardFilterDiagnosticsError(ValueError):
    """Raised when forward filter diagnostics cannot be built."""


@dataclass(frozen=True, slots=True)
class DiagnosticStreamConfig:
    name: str
    issue_id: str
    pack_manifest_path: Path
    features_path: Path
    forward_run_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DiagnosticStreamConfig:
        return cls(
            name=str(payload["name"]),
            issue_id=str(payload["issue_id"]),
            pack_manifest_path=Path(str(payload["pack_manifest_path"])),
            features_path=Path(str(payload["features_path"])),
            forward_run_path=Path(str(payload["forward_run_path"])),
        )


@dataclass(frozen=True, slots=True)
class ForwardFilterDiagnosticsConfig:
    report_name: str
    issue_id: str
    epic_id: str
    output_json_path: Path
    output_markdown_path: Path
    streams: tuple[DiagnosticStreamConfig, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ForwardFilterDiagnosticsConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            streams=tuple(
                DiagnosticStreamConfig.from_dict(dict(item)) for item in payload["streams"]
            ),
        )

    @classmethod
    def from_path(cls, path: Path) -> ForwardFilterDiagnosticsConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_forward_filter_diagnostics(config: ForwardFilterDiagnosticsConfig) -> dict[str, object]:
    """Build filter pass/fail diagnostics for configured forward paper streams."""

    _validate_config(config)
    stream_reports = [_stream_report(stream) for stream in config.streams]
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "streams": stream_reports,
        "summary": {
            "stream_count": len(stream_reports),
            "total_strategy_rows": sum(
                _int(stream["strategy_row_count"]) for stream in stream_reports
            ),
            "total_final_candidate_rows": sum(
                _int(stream["final_candidate_count"]) for stream in stream_reports
            ),
        },
        "decision": {
            "working_model": False,
            "live_trading_approved": False,
            "notes": "Research-only diagnostics; does not change filters or promote a model.",
        },
    }
    _write_report(config, payload)
    return payload


def _stream_report(config: DiagnosticStreamConfig) -> dict[str, object]:
    pack = _read_json(config.pack_manifest_path)
    forward_run = _read_json(config.forward_run_path)
    rows = [dict(row) for row in pq.read_table(config.features_path).to_pylist()]
    strategy = dict(pack["strategy"])
    symbols = {str(symbol) for symbol in strategy.get("symbols", ())}
    filters = [dict(item) for item in strategy.get("filters", ())]
    strategy_rows = [row for row in rows if str(row.get("symbol")) in symbols]
    sequential_rows = strategy_rows
    filter_reports: list[dict[str, object]] = []

    for item in filters:
        feature = str(item["feature"])
        independent_pass_rows = [row for row in strategy_rows if _filter_passes(row, item)]
        independent_missing_count = sum(1 for row in strategy_rows if row.get(feature) is None)
        before_count = len(sequential_rows)
        sequential_rows = [row for row in sequential_rows if _filter_passes(row, item)]
        values = [_number(row.get(feature)) for row in strategy_rows]
        numeric_values = [value for value in values if value is not None]
        filter_reports.append(
            {
                "feature": feature,
                "operator": str(item["operator"]),
                "threshold": float(item["value"]),
                "independent_pass_count": len(independent_pass_rows),
                "independent_missing_count": independent_missing_count,
                "sequential_before_count": before_count,
                "sequential_after_count": len(sequential_rows),
                "sequential_rejected_count": before_count - len(sequential_rows),
                "min_value": min(numeric_values) if numeric_values else None,
                "max_value": max(numeric_values) if numeric_values else None,
            }
        )

    return {
        "name": config.name,
        "issue_id": config.issue_id,
        "pack_manifest_path": str(config.pack_manifest_path),
        "features_path": str(config.features_path),
        "forward_run_path": str(config.forward_run_path),
        "decision_time": _nested_text(forward_run, ("collector_summary", "decision_time")),
        "reported_candidate_count": _nested_int(
            forward_run, ("collector_summary", "candidate_count")
        ),
        "feature_row_count": len(rows),
        "strategy_symbols": sorted(symbols),
        "strategy_row_count": len(strategy_rows),
        "final_candidate_count": len(sequential_rows),
        "final_candidate_symbols": sorted(str(row.get("symbol")) for row in sequential_rows),
        "filters": filter_reports,
    }


def _filter_passes(row: dict[str, object], item: dict[str, object]) -> bool:
    value = _number(row.get(str(item["feature"])))
    if value is None:
        return False
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
    raise ForwardFilterDiagnosticsError(f"unsupported filter operator: {operator}")


def _write_report(config: ForwardFilterDiagnosticsConfig, payload: dict[str, object]) -> None:
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        "## Streams",
        "",
    ]
    for stream in payload["streams"]:
        item = dict(stream)
        lines.extend(
            [
                f"### {item['name']}",
                "",
                f"- decision time: `{item['decision_time']}`",
                f"- strategy rows: `{item['strategy_row_count']}`",
                f"- final candidates: `{item['final_candidate_count']}`",
                "",
            ]
        )
        for filter_item in item["filters"]:
            current = dict(filter_item)
            lines.append(
                "- "
                f"`{current['feature']} {current['operator']} {current['threshold']}`: "
                f"independent `{current['independent_pass_count']}`, "
                f"sequential `{current['sequential_before_count']}` -> "
                f"`{current['sequential_after_count']}`, "
                f"missing `{current['independent_missing_count']}`"
            )
        lines.append("")
    lines.extend(
        [
            "## Decision",
            "",
            "Research-only diagnostics. No filters are changed and no live trading is approved.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_config(config: ForwardFilterDiagnosticsConfig) -> None:
    if not config.streams:
        raise ForwardFilterDiagnosticsError("streams must not be empty")


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise ForwardFilterDiagnosticsError(f"missing JSON input: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ForwardFilterDiagnosticsError(f"JSON input must be an object: {path}")
    return payload


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    return float(value)


def _nested_text(payload: dict[str, object], path: tuple[str, ...]) -> str:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return "" if current is None else str(current)


def _nested_int(payload: dict[str, object], path: tuple[str, ...]) -> int:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return 0
        current = current.get(key)
    return _int(current)


def _int(value: object) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    payload = build_forward_filter_diagnostics(
        ForwardFilterDiagnosticsConfig.from_path(args.config)
    )
    print(json.dumps(payload["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
