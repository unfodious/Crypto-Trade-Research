"""Summarize research-only droplet stream health from generated run artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = "research.droplet_stream_health.v1"

SystemdReader = Callable[[str], dict[str, object]]


def build_research_stream_health_report(
    *,
    root: Path,
    include_systemd: bool = True,
    systemd_reader: SystemdReader | None = None,
) -> dict[str, object]:
    """Build a compact health report for the active CT-113 research droplet streams."""

    reader = systemd_reader or _read_systemd_unit
    streams = {
        "ct145_forward_paper": _build_ct145_summary(root, include_systemd, reader),
        "ct156_shadow_forward_paper": _build_ct156_summary(root, include_systemd, reader),
        "ct149_whale_watchlist": _build_ct149_summary(root, include_systemd, reader),
        "ct151_binance_crowding": _build_ct151_summary(root, include_systemd, reader),
        "ct158_binance_order_book": _build_ct158_summary(root, include_systemd, reader),
        "ct160_binance_liquidations": _build_ct160_summary(root, include_systemd, reader),
        "ct162_external_forward_features": _build_ct162_summary(root, include_systemd, reader),
    }
    health_warnings = [
        warning
        for stream in streams.values()
        for warning in _stream_health_warnings(stream)
        if warning
    ]
    source_warnings = [
        warning
        for stream in streams.values()
        for warning in _stream_source_warnings(stream)
        if warning
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "root": str(root),
        "overall_status": "warning" if health_warnings else "ok",
        "streams": streams,
        "warnings": health_warnings,
        "source_warnings": source_warnings,
        "notes": "Research-only health summary. No orders are submitted or modified.",
    }


def _build_ct145_summary(
    root: Path,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    return _build_forward_paper_summary(
        root=root,
        issue_id="CT-146",
        source_issue_id="CT-145",
        service_unit="ct145-forward-paper.service",
        timer_unit="ct145-forward-paper.timer",
        output_path=Path("data/generated/ct145_no_ton_negative_funding_forward_paper"),
        include_systemd=include_systemd,
        systemd_reader=systemd_reader,
    )


def _build_ct156_summary(
    root: Path,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    return _build_forward_paper_summary(
        root=root,
        issue_id="CT-156",
        source_issue_id="CT-155",
        service_unit="ct156-forward-paper.service",
        timer_unit="ct156-forward-paper.timer",
        output_path=Path("data/generated/ct156_high_beta_dot_shadow_forward_paper"),
        include_systemd=include_systemd,
        systemd_reader=systemd_reader,
    )


def _build_forward_paper_summary(
    *,
    root: Path,
    issue_id: str,
    source_issue_id: str,
    service_unit: str,
    timer_unit: str,
    output_path: Path,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    forward_run_path = root / output_path / "forward_run.json"
    monitoring_path = root / output_path / "monitoring_report.json"
    forward_run = _read_json(forward_run_path)
    monitoring = _read_json(monitoring_path)
    stream = {
        "issue_id": issue_id,
        "source_issue_id": source_issue_id,
        "service_unit": service_unit,
        "timer_unit": timer_unit,
        "forward_run_path": str(forward_run_path),
        "monitoring_report_path": str(monitoring_path),
        "service": _unit_summary(service_unit, include_systemd, systemd_reader),
        "timer": _unit_summary(timer_unit, include_systemd, systemd_reader),
        "latest_decision_time": _nested_text(forward_run, ("collector_summary", "decision_time")),
        "collector_summary": _nested_dict(forward_run, ("collector_summary",)),
        "row_counts": _nested_dict(forward_run, ("row_counts",)),
        "monitoring_status": _text(monitoring.get("monitoring_status")),
        "decision": _nested_dict(monitoring, ("decision",)),
        "metrics": _forward_paper_metrics(monitoring),
        "source_warnings": list(_nested_list(monitoring, ("warnings",))),
        "health_warnings": [],
    }
    _add_missing_file_warnings(stream, forward_run_path, monitoring_path)
    return stream


def _build_ct149_summary(
    root: Path,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    run_path = root / "data/generated/ct134_hyperliquid_whale_watchlist/watchlist_run.json"
    run = _read_json(run_path)
    latest_snapshot = _latest_snapshot(run)
    stream = {
        "issue_id": "CT-150",
        "source_issue_id": "CT-149",
        "service_unit": "ct149-hyperliquid-whale-watchlist.service",
        "timer_unit": "ct149-hyperliquid-whale-watchlist.timer",
        "watchlist_run_path": str(run_path),
        "service": _unit_summary(
            "ct149-hyperliquid-whale-watchlist.service", include_systemd, systemd_reader
        ),
        "timer": _unit_summary(
            "ct149-hyperliquid-whale-watchlist.timer", include_systemd, systemd_reader
        ),
        "created_at": _text(run.get("created_at")),
        "alert_count": _int(run.get("alert_count")),
        "latest_snapshot": {
            "generated_at": _text(latest_snapshot.get("generated_at")),
            "position_count": _int(latest_snapshot.get("position_count")),
            "fill_count": _int(latest_snapshot.get("fill_count")),
            "alert_count": _int(latest_snapshot.get("alert_count")),
            "warning_count": _int(latest_snapshot.get("warning_count")),
        },
        "source_warnings": list(_nested_list(run, ("alerts",)))
        + list(_nested_list(latest_snapshot, ("warnings",))),
        "health_warnings": [],
    }
    _add_missing_file_warnings(stream, run_path)
    return stream


def _build_ct151_summary(
    root: Path,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    run_path = root / "data/generated/ct151_binance_crowding_forward/crowding_run.json"
    run = _read_json(run_path)
    stream = {
        "issue_id": "CT-152",
        "source_issue_id": "CT-151/CT-153",
        "service_unit": "ct151-binance-crowding-snapshot.service",
        "timer_unit": "ct151-binance-crowding-snapshot.timer",
        "crowding_run_path": str(run_path),
        "service": _unit_summary(
            "ct151-binance-crowding-snapshot.service", include_systemd, systemd_reader
        ),
        "timer": _unit_summary(
            "ct151-binance-crowding-snapshot.timer", include_systemd, systemd_reader
        ),
        "latest_generated_at": _text(run.get("latest_generated_at")),
        "generator_version": _text(run.get("generator_version")),
        "row_count": _int(run.get("row_count")),
        "period": _text(run.get("period")),
        "symbol_count": len(_nested_list(run, ("symbols",))),
        "source_warnings": list(_nested_list(run, ("warnings",))),
        "health_warnings": [],
    }
    if stream["row_count"] != 55:
        stream["health_warnings"].append("expected CT-153 healthy row_count=55")
    _add_missing_file_warnings(stream, run_path)
    return stream


def _build_ct158_summary(
    root: Path,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    run_path = root / "data/generated/ct158_binance_order_book_forward/order_book_run.json"
    run = _read_json(run_path)
    stream = {
        "issue_id": "CT-159",
        "source_issue_id": "CT-158",
        "service_unit": "ct158-binance-order-book-snapshot.service",
        "timer_unit": "ct158-binance-order-book-snapshot.timer",
        "order_book_run_path": str(run_path),
        "service": _unit_summary(
            "ct158-binance-order-book-snapshot.service", include_systemd, systemd_reader
        ),
        "timer": _unit_summary(
            "ct158-binance-order-book-snapshot.timer", include_systemd, systemd_reader
        ),
        "latest_generated_at": _text(run.get("latest_generated_at")),
        "generator_version": _text(run.get("generator_version")),
        "row_count": _int(run.get("row_count")),
        "summary_row_count": _int(run.get("summary_row_count")),
        "level_row_count": _int(run.get("level_row_count")),
        "depth_limit": _int(run.get("depth_limit")),
        "symbol_count": len(_nested_list(run, ("symbols",))),
        "source_warnings": list(_nested_list(run, ("warnings",))),
        "health_warnings": [],
    }
    if stream["row_count"] != 451:
        stream["health_warnings"].append("expected CT-158 healthy row_count=451")
    _add_missing_file_warnings(stream, run_path)
    return stream


def _build_ct160_summary(
    root: Path,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    run_path = root / "data/generated/ct160_binance_liquidations_forward/liquidation_run.json"
    run = _read_json(run_path)
    stream = {
        "issue_id": "CT-161",
        "source_issue_id": "CT-160",
        "service_unit": "ct160-binance-liquidation-snapshot.service",
        "timer_unit": "ct160-binance-liquidation-snapshot.timer",
        "liquidation_run_path": str(run_path),
        "service": _unit_summary(
            "ct160-binance-liquidation-snapshot.service", include_systemd, systemd_reader
        ),
        "timer": _unit_summary(
            "ct160-binance-liquidation-snapshot.timer", include_systemd, systemd_reader
        ),
        "latest_generated_at": _text(run.get("latest_generated_at")),
        "capture_started_at": _text(run.get("capture_started_at")),
        "capture_ended_at": _text(run.get("capture_ended_at")),
        "generator_version": _text(run.get("generator_version")),
        "row_count": _int(run.get("row_count")),
        "event_count_total": _int(run.get("event_count_total")),
        "event_count_filtered_out": _int(run.get("event_count_filtered_out")),
        "symbol_count": len(_nested_list(run, ("symbols",))),
        "source_warnings": list(_nested_list(run, ("warnings",))),
        "health_warnings": [],
    }
    _add_missing_file_warnings(stream, run_path)
    return stream


def _build_ct162_summary(
    root: Path,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    run_path = (
        root / "data/generated/ct162_external_forward_features/external_forward_features_run.json"
    )
    run = _read_json(run_path)
    stream = {
        "issue_id": "CT-163",
        "source_issue_id": "CT-162",
        "service_unit": "ct162-external-forward-features.service",
        "timer_unit": "ct162-external-forward-features.timer",
        "external_forward_features_run_path": str(run_path),
        "service": _unit_summary(
            "ct162-external-forward-features.service", include_systemd, systemd_reader
        ),
        "timer": _unit_summary(
            "ct162-external-forward-features.timer", include_systemd, systemd_reader
        ),
        "latest_generated_at": _text(run.get("latest_generated_at")),
        "generator_version": _text(run.get("generator_version")),
        "row_count": _int(run.get("row_count")),
        "crowding_snapshot_count": _int(run.get("crowding_snapshot_count")),
        "order_book_snapshot_count": _int(run.get("order_book_snapshot_count")),
        "liquidation_snapshot_count": _int(run.get("liquidation_snapshot_count")),
        "symbol_count": len(_nested_list(run, ("symbols",))),
        "source_warnings": list(_nested_list(run, ("warnings",))),
        "health_warnings": [],
    }
    if stream["row_count"] <= 0:
        stream["health_warnings"].append("expected CT-162 row_count > 0")
    _add_missing_file_warnings(stream, run_path)
    return stream


def _unit_summary(
    unit: str,
    include_systemd: bool,
    systemd_reader: SystemdReader,
) -> dict[str, object]:
    if not include_systemd:
        return {"checked": False}
    try:
        state = systemd_reader(unit)
    except Exception as exc:  # noqa: BLE001 - health report should degrade to warning.
        return {"checked": True, "unit": unit, "error": str(exc)}
    return {"checked": True, "unit": unit, **state}


def _read_systemd_unit(unit: str) -> dict[str, object]:
    result = subprocess.run(
        [
            "systemctl",
            "show",
            unit,
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "Result",
            "-p",
            "ExecMainStatus",
            "--no-pager",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    parsed: dict[str, object] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            parsed[_snake_case(key)] = value
    return parsed


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def _stream_health_warnings(stream: dict[str, object]) -> list[str]:
    warnings = [str(warning) for warning in stream.get("health_warnings", [])]
    for unit_key in ("service", "timer"):
        unit = stream.get(unit_key)
        if not isinstance(unit, dict) or not unit.get("checked"):
            continue
        if unit.get("error"):
            warnings.append(f"{stream['issue_id']} {unit_key} check failed: {unit['error']}")
        active_state = unit.get("active_state")
        unit_name = str(unit.get("unit", ""))
        is_timer = unit_name.endswith(".timer")
        is_failed_service = (
            unit_name.endswith(".service")
            and unit.get("result")
            and unit.get("result") != "success"
        )
        if is_timer and active_state and active_state != "active":
            warnings.append(f"{stream['issue_id']} {unit_key} is {unit.get('active_state')}")
        if is_failed_service:
            warnings.append(f"{stream['issue_id']} {unit_key} result is {unit.get('result')}")
    return warnings


def _stream_source_warnings(stream: dict[str, object]) -> list[str]:
    return [str(warning) for warning in stream.get("source_warnings", [])]


def _add_missing_file_warnings(stream: dict[str, object], *paths: Path) -> None:
    warnings = stream.setdefault("health_warnings", [])
    if not isinstance(warnings, list):
        raise TypeError("stream warnings must be a list")
    for path in paths:
        if not path.exists():
            warnings.append(f"missing file: {path}")


def _latest_snapshot(run: dict[str, object]) -> dict[str, object]:
    snapshots = _nested_list(run, ("snapshots",))
    if not snapshots:
        return {}
    snapshot = snapshots[-1]
    if isinstance(snapshot, dict):
        return snapshot
    return {}


def _forward_paper_metrics(monitoring: dict[str, object]) -> dict[str, object]:
    metrics = _nested_dict(monitoring, ("metrics",))
    return {
        "trade_count": _int(metrics.get("trade_count")),
        "open_trade_count": _int(metrics.get("open_trade_count")),
        "average_r_after_costs": _float(metrics.get("average_r_after_costs")),
        "max_drawdown_pct": _float(metrics.get("max_drawdown_pct")),
        "reached_1_0r_then_lost_count": _int(metrics.get("reached_1_0r_then_lost_count")),
        "counterfactual_exit_metrics": _nested_dict(metrics, ("counterfactual_exit_metrics",)),
    }


def _nested_dict(payload: dict[str, object], path: tuple[str, ...]) -> dict[str, object]:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    if isinstance(current, dict):
        return current
    return {}


def _nested_list(payload: dict[str, object], path: tuple[str, ...]) -> list[object]:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    if isinstance(current, list):
        return current
    return []


def _nested_text(payload: dict[str, object], path: tuple[str, ...]) -> str:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return _text(current)


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _int(value: object) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def _float(value: object) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def _snake_case(value: str) -> str:
    result = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--skip-systemd",
        action="store_true",
        help="Read generated artifacts only, without calling systemctl.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = build_research_stream_health_report(
        root=args.root,
        include_systemd=not args.skip_systemd,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
