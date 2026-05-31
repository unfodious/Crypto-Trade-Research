"""Screen spot rotation positions against point-in-time futures metrics context."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_trade_research.futures_metrics_selected_features import (
    _feature_row,
    _load_metrics_index,
)
from crypto_trade_research.spot_drawdown_swing import (
    SpotDrawdownSwingConfig,
    build_spot_drawdown_swing_positions,
)

SCHEMA_VERSION = "research.external-rotation-screen.v1"


class ExternalRotationScreenError(ValueError):
    """Raised when an external rotation screen cannot be built."""


@dataclass(frozen=True, slots=True)
class ExternalRotationFilter:
    feature: str
    operator: str
    value: float | int | str | bool

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExternalRotationFilter:
        return cls(
            feature=str(payload["feature"]),
            operator=str(payload["operator"]),
            value=payload["value"],
        )


@dataclass(frozen=True, slots=True)
class ExternalRotationRule:
    name: str
    description: str
    require_metrics_match: bool
    filter_groups: tuple[tuple[ExternalRotationFilter, ...], ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExternalRotationRule:
        groups_payload = payload.get("filter_groups")
        if groups_payload is None and "filters" in payload:
            groups_payload = [payload["filters"]]
        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            require_metrics_match=bool(payload.get("require_metrics_match", False)),
            filter_groups=tuple(
                tuple(ExternalRotationFilter.from_dict(dict(item)) for item in group)
                for group in (groups_payload or [])
            ),
        )


@dataclass(frozen=True, slots=True)
class ExternalRotationScreenConfig:
    report_name: str
    issue_id: str
    epic_id: str
    spot_config_path: Path
    scenario_names: tuple[str, ...]
    metrics_path: Path
    max_metrics_age_minutes: int
    output_json_path: Path
    output_markdown_path: Path
    rules: tuple[ExternalRotationRule, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExternalRotationScreenConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            spot_config_path=Path(str(payload["spot_config_path"])),
            scenario_names=tuple(str(item) for item in payload["scenario_names"]),
            metrics_path=Path(str(payload["metrics_path"])),
            max_metrics_age_minutes=int(payload.get("max_metrics_age_minutes", 10)),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            rules=tuple(ExternalRotationRule.from_dict(dict(item)) for item in payload["rules"]),
        )

    @classmethod
    def from_path(cls, path: Path) -> ExternalRotationScreenConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_external_rotation_screen_report(
    config: ExternalRotationScreenConfig,
) -> dict[str, object]:
    """Build selected-position diagnostics for external-context rotation filters."""

    if not config.scenario_names:
        raise ExternalRotationScreenError("scenario_names must not be empty")
    if not config.rules:
        raise ExternalRotationScreenError("rules must not be empty")
    if config.max_metrics_age_minutes <= 0:
        raise ExternalRotationScreenError("max_metrics_age_minutes must be positive")

    spot_config = SpotDrawdownSwingConfig.from_path(config.spot_config_path)
    known_scenarios = {scenario.name for scenario in spot_config.scenarios}
    missing_scenarios = sorted(set(config.scenario_names) - known_scenarios)
    if missing_scenarios:
        raise ExternalRotationScreenError(f"unknown spot scenarios: {missing_scenarios}")

    positions = build_spot_drawdown_swing_positions(
        spot_config,
        scenario_names=set(config.scenario_names),
    )
    metrics_index = _load_metrics_index(config.metrics_path, config.max_metrics_age_minutes)
    timeframe = f"{spot_config.timeframe_minutes}m"
    enriched = [_enriched_position(position, metrics_index, timeframe) for position in positions]

    scenarios = []
    for scenario_name in config.scenario_names:
        scenario_rows = [row for row in enriched if str(row["scenario"]) == scenario_name]
        scenarios.append(
            {
                "name": scenario_name,
                "position_count": len(scenario_rows),
                "matched_metrics_count": sum(
                    1 for row in scenario_rows if int(row["fm_metrics_match"]) == 1
                ),
                "rules": [_rule_report(rule, scenario_rows) for rule in config.rules],
            }
        )

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "spot_config_path": str(config.spot_config_path),
        "metrics_path": str(config.metrics_path),
        "max_metrics_age_minutes": config.max_metrics_age_minutes,
        "scenario_names": list(config.scenario_names),
        "screen_note": (
            "Selected-position diagnostic only. It is point-in-time for futures metrics, "
            "but it does not recompute portfolio cash, open-position contention, or later "
            "rotation paths after an entry is skipped."
        ),
        "scenarios": scenarios,
        "decision": _decision(scenarios),
    }
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")
    return payload


def _enriched_position(
    position: dict[str, object],
    metrics_index: object,
    timeframe: str,
) -> dict[str, object]:
    entry_time = _as_datetime(position["entry_time"])
    features = _feature_row(
        {
            "symbol": str(position["symbol"]),
            "timeframe": timeframe,
            "decision_time": entry_time,
        },
        metrics_index,  # type: ignore[arg-type]
    )
    return {
        **position,
        **features,
        "entry_time": _format_timestamp(entry_time),
    }


def _rule_report(rule: ExternalRotationRule, rows: list[dict[str, object]]) -> dict[str, object]:
    eligible = [
        row for row in rows if not rule.require_metrics_match or int(row["fm_metrics_match"]) == 1
    ]
    kept = [row for row in eligible if not _rule_matches(rule, row)]
    skipped = [row for row in eligible if _rule_matches(rule, row)]
    return {
        "name": rule.name,
        "description": rule.description,
        "require_metrics_match": rule.require_metrics_match,
        "input_position_count": len(rows),
        "eligible_position_count": len(eligible),
        "missing_metrics_excluded_count": len(rows) - len(eligible),
        "kept_position_count": len(kept),
        "skipped_position_count": len(skipped),
        "skipped_return_metrics": _position_metrics(skipped),
        "kept_return_metrics": _position_metrics(kept),
        "windows": [
            {
                "name": window,
                "metrics": _position_metrics([row for row in kept if str(row["window"]) == window]),
            }
            for window in sorted({str(row["window"]) for row in rows})
        ],
        "symbols": [
            {
                "symbol": symbol,
                "metrics": _position_metrics([row for row in kept if str(row["symbol"]) == symbol]),
            }
            for symbol in sorted({str(row["symbol"]) for row in rows})
        ],
    }


def _rule_matches(rule: ExternalRotationRule, row: dict[str, object]) -> bool:
    return any(_group_matches(group, row) for group in rule.filter_groups)


def _group_matches(
    group: tuple[ExternalRotationFilter, ...],
    row: dict[str, object],
) -> bool:
    return bool(group) and all(_filter_matches(item, row) for item in group)


def _filter_matches(item: ExternalRotationFilter, row: dict[str, object]) -> bool:
    value = row.get(item.feature)
    if value is None:
        return False
    left = _coerce_comparable(value)
    right = _coerce_comparable(item.value)
    if item.operator == "<":
        return left < right
    if item.operator == "<=":
        return left <= right
    if item.operator == ">":
        return left > right
    if item.operator == ">=":
        return left >= right
    if item.operator == "==":
        return left == right
    if item.operator == "!=":
        return left != right
    raise ExternalRotationScreenError(f"unsupported filter operator: {item.operator}")


def _position_metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    returns = [_as_float(row["net_return_pct"]) for row in rows]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    pnl = [
        _as_float(row.get("exit_value_usd", 0.0)) - _as_float(row.get("cost_usd", 0.0))
        for row in rows
    ]
    windows = _group_returns(rows, "window")
    symbols = _group_returns(rows, "symbol")
    return {
        "position_count": len(rows),
        "closed_position_count": sum(1 for row in rows if row.get("status") == "closed"),
        "open_position_count": sum(1 for row in rows if row.get("status") == "open"),
        "average_net_return_pct": _mean(returns),
        "median_net_return_pct": _median(returns),
        "win_rate": len(wins) / len(returns) if returns else 0.0,
        "profit_factor": _profit_factor(returns),
        "total_cost_usd": sum(_as_float(row.get("cost_usd", 0.0)) for row in rows),
        "total_net_pnl_usd": sum(pnl),
        "average_max_adverse_pct": _mean(
            [_as_float(row.get("max_adverse_pct", 0.0)) for row in rows]
        ),
        "average_max_favorable_pct": _mean(
            [_as_float(row.get("max_favorable_pct", 0.0)) for row in rows]
        ),
        "positive_window_breadth": _positive_breadth(windows),
        "positive_symbol_breadth": _positive_breadth(symbols),
        "loss_count": len(losses),
        "win_count": len(wins),
    }


def _group_returns(rows: list[dict[str, object]], field: str) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(str(row[field]), []).append(_as_float(row["net_return_pct"]))
    return grouped


def _positive_breadth(grouped: dict[str, list[float]]) -> float:
    if not grouped:
        return 0.0
    return sum(_mean(values) > 0 for values in grouped.values()) / len(grouped)


def _decision(scenarios: list[dict[str, object]]) -> dict[str, object]:
    improvements = []
    for scenario in scenarios:
        rules = list(scenario["rules"])  # type: ignore[index]
        matched_base = next(
            (dict(rule) for rule in rules if dict(rule)["name"] == "metrics_matched_base"),
            None,
        )
        if matched_base is None:
            continue
        base_metrics = dict(matched_base["kept_return_metrics"])
        base_average = _as_float(base_metrics["average_net_return_pct"])
        for rule in rules:
            rule_item = dict(rule)
            if rule_item["name"] in {"no_external_screen", "metrics_matched_base"}:
                continue
            metrics = dict(rule_item["kept_return_metrics"])
            improvements.append(
                {
                    "scenario": scenario["name"],
                    "rule": rule_item["name"],
                    "kept_position_count": metrics["position_count"],
                    "average_net_return_delta_pct": _as_float(metrics["average_net_return_pct"])
                    - base_average,
                    "positive_window_breadth": metrics["positive_window_breadth"],
                }
            )
    candidates = [
        item
        for item in improvements
        if int(item["kept_position_count"]) >= 20
        and _as_float(item["average_net_return_delta_pct"]) > 0
        and _as_float(item["positive_window_breadth"]) >= 0.75
    ]
    return {
        "candidate_rule_count": len(candidates),
        "candidate_rules": candidates,
        "recommendation": (
            "promote_to_full_replay_if_portfolio_path_is_recomputed"
            if candidates
            else "reject_external_screen_until_stronger_selected_position_edge"
        ),
    }


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"- Issue: `{payload['issue_id']}`",
        f"- Epic: `{payload['epic_id']}`",
        f"- Spot config: `{payload['spot_config_path']}`",
        f"- Metrics: `{payload['metrics_path']}`",
        f"- Note: {payload['screen_note']}",
        "",
        "## Decision",
        "",
        f"- Recommendation: `{dict(payload['decision'])['recommendation']}`",
        f"- Candidate rules: `{dict(payload['decision'])['candidate_rule_count']}`",
        "",
        "## Scenario Results",
        "",
    ]
    for scenario in payload["scenarios"]:  # type: ignore[index]
        scenario_item = dict(scenario)
        lines.extend(
            [
                f"### {scenario_item['name']}",
                "",
                f"- Positions: `{scenario_item['position_count']}`",
                f"- Matched metrics: `{scenario_item['matched_metrics_count']}`",
                "",
                (
                    "| Rule | Eligible | Kept | Skipped | Avg return | Win rate | "
                    "PF | PnL USD | Window breadth | Symbol breadth |"
                ),
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for rule in scenario_item["rules"]:
            rule_item = dict(rule)
            metrics = dict(rule_item["kept_return_metrics"])
            lines.append(
                "| "
                f"{rule_item['name']} | "
                f"{rule_item['eligible_position_count']} | "
                f"{rule_item['kept_position_count']} | "
                f"{rule_item['skipped_position_count']} | "
                f"{_format_pct(_as_float(metrics['average_net_return_pct']))} | "
                f"{_format_pct(_as_float(metrics['win_rate']))} | "
                f"{_format_float(metrics['profit_factor'])} | "
                f"{_format_float(metrics['total_net_pnl_usd'])} | "
                f"{_format_pct(_as_float(metrics['positive_window_breadth']))} | "
                f"{_format_pct(_as_float(metrics['positive_symbol_breadth']))} |"
            )
        lines.extend(["", ""])
    lines.extend(
        [
            "## Interpretation",
            "",
            (
                "This screen is intentionally conservative: futures metrics are joined only from "
                "the last available row at or before the spot entry timestamp, with the configured "
                "maximum age. A passing row here is not a paper-trading candidate by itself "
                "because skipped entries can change later cash availability and rotation choices."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _coerce_comparable(value: object) -> float | str | bool:
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int | float):
        return float(value)
    return str(value)


def _profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses > 0:
        return gains / losses
    return math.inf if gains > 0 else None


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _as_float(value: object) -> float:
    return float(value)


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _format_pct(value: float) -> str:
    return f"{value:.2%}"


def _format_float(value: object) -> str:
    if value is None:
        return "n/a"
    numeric = _as_float(value)
    if math.isinf(numeric):
        return "inf"
    return f"{numeric:.4f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_external_rotation_screen_report(
        ExternalRotationScreenConfig.from_path(args.config)
    )
    decision = dict(payload["decision"])
    print(
        f"{payload['report_name']}: recommendation={decision['recommendation']} "
        f"candidate_rules={decision['candidate_rule_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
