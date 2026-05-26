"""Promotion stability gates for candidate selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal


@dataclass(frozen=True, slots=True)
class StabilityThresholds:
    max_drawdown_pct: float = 0.08
    min_trade_count: int = 100
    min_positive_symbol_fraction: float = 0.50
    min_positive_session_fraction: float = 0.50
    max_top_day_profit_share: float = 0.75
    min_positive_nearby_fraction: float = 0.50


@dataclass(frozen=True, slots=True)
class StabilityGateResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class StabilityReport:
    schema_version: str
    candidate_name: str
    status: Literal["pass", "reject"]
    gates: tuple[StabilityGateResult, ...]
    thresholds: StabilityThresholds
    created_at: str

    def to_report_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_name": self.candidate_name,
            "status": self.status,
            "gates": [asdict(gate) for gate in self.gates],
            "thresholds": asdict(self.thresholds),
            "created_at": self.created_at,
        }


def evaluate_candidate_stability(
    *,
    candidate_row: dict[str, object],
    leaderboard_rows: list[dict[str, object]],
    segment_breakdown: dict[str, object],
    thresholds: StabilityThresholds | None = None,
) -> StabilityReport:
    """Evaluate whether a candidate is stable enough for paper-trading promotion."""

    thresholds = thresholds or StabilityThresholds()
    model_average_r = _float(candidate_row.get("oos_model_average_r"))
    rule_only_average_r = _float(candidate_row.get("oos_rule_only_average_r"))
    trade_count = _int(candidate_row.get("trade_count"))
    max_drawdown_pct = _float(candidate_row.get("max_drawdown_pct"))
    gates = (
        StabilityGateResult(
            "positive_oos_expectancy",
            model_average_r > 0,
            f"model OOS average R must be positive ({model_average_r:.4f} > 0)",
        ),
        StabilityGateResult(
            "beats_rule_only_oos",
            model_average_r > rule_only_average_r,
            (
                "model OOS average R must beat rule-only "
                f"({model_average_r:.4f} > {rule_only_average_r:.4f})"
            ),
        ),
        StabilityGateResult(
            "minimum_trade_count",
            trade_count >= thresholds.min_trade_count,
            (
                "aggregate trade count must be meaningful "
                f"({trade_count} >= {thresholds.min_trade_count})"
            ),
        ),
        StabilityGateResult(
            "drawdown_within_limit",
            max_drawdown_pct <= thresholds.max_drawdown_pct,
            (
                "max drawdown must stay within limit "
                f"({max_drawdown_pct:.4%} <= {thresholds.max_drawdown_pct:.4%})"
            ),
        ),
        _breadth_gate(
            "symbol_breadth",
            _segment(segment_breakdown, "model_by_symbol"),
            thresholds.min_positive_symbol_fraction,
        ),
        _breadth_gate(
            "session_breadth",
            _segment(segment_breakdown, "model_by_session"),
            thresholds.min_positive_session_fraction,
        ),
        _top_day_gate(
            _segment(segment_breakdown, "model_by_day"),
            thresholds.max_top_day_profit_share,
        ),
        _nearby_sensitivity_gate(leaderboard_rows, thresholds.min_positive_nearby_fraction),
    )
    failed = [gate.name for gate in gates if not gate.passed]
    return StabilityReport(
        schema_version="research.stability-report.v1",
        candidate_name=str(candidate_row.get("experiment_name", "unknown")),
        status="reject" if failed else "pass",
        gates=gates,
        thresholds=thresholds,
        created_at=_format_timestamp(datetime.now(UTC)),
    )


def _breadth_gate(
    name: str,
    segment: dict[str, dict[str, object]],
    required_fraction: float,
) -> StabilityGateResult:
    eligible = [values for values in segment.values() if _int(values.get("trade_count")) > 0]
    positive = [values for values in eligible if _float(values.get("average_r")) > 0]
    fraction = len(positive) / len(eligible) if eligible else 0.0
    return StabilityGateResult(
        name,
        fraction >= required_fraction,
        (
            f"positive slice fraction must be broad enough "
            f"({fraction:.2%} >= {required_fraction:.2%})"
        ),
    )


def _top_day_gate(
    day_segment: dict[str, dict[str, object]],
    max_share: float,
) -> StabilityGateResult:
    positive_values = [
        _float(values.get("average_r")) * _int(values.get("trade_count"))
        for values in day_segment.values()
        if _float(values.get("average_r")) > 0 and _int(values.get("trade_count")) > 0
    ]
    total_positive = sum(positive_values)
    top_share = max(positive_values) / total_positive if total_positive > 0 else 0.0
    return StabilityGateResult(
        "lucky_day_concentration",
        total_positive > 0 and top_share <= max_share,
        (
            "positive expectancy must not come from a single lucky day "
            f"(top share {top_share:.2%} <= {max_share:.2%})"
        ),
    )


def _nearby_sensitivity_gate(
    rows: list[dict[str, object]],
    required_fraction: float,
) -> StabilityGateResult:
    eligible = [row for row in rows if _int(row.get("trade_count")) > 0]
    positive = [row for row in eligible if _float(row.get("oos_model_average_r")) > 0]
    fraction = len(positive) / len(eligible) if eligible else 0.0
    return StabilityGateResult(
        "nearby_sensitivity",
        fraction >= required_fraction,
        (
            "nearby threshold/horizon variants must stay positive often enough "
            f"({fraction:.2%} >= {required_fraction:.2%})"
        ),
    )


def _segment(
    segment_breakdown: dict[str, object],
    name: str,
) -> dict[str, dict[str, object]]:
    raw = segment_breakdown.get(name, {})
    return {str(key): dict(value) for key, value in dict(raw).items()}


def _float(value: object) -> float:
    return float(value) if value is not None else 0.0


def _int(value: object) -> int:
    return int(value) if value is not None else 0


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
