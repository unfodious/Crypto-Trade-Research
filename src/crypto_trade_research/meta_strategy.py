"""Research-only meta-strategy decision layer."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime

from crypto_trade_research.backtest import (
    BacktestConfig,
    BacktestReport,
    SignalRow,
    evaluate_signal_strategy,
)


@dataclass(frozen=True, slots=True)
class CandidateSetup:
    decision_time: datetime
    symbol: str
    timeframe: str
    setup_type: str
    side: str
    deterministic_score: float
    rule_only_gross_r: float


@dataclass(frozen=True, slots=True)
class CandidateKey:
    decision_time: datetime
    symbol: str
    timeframe: str
    setup_type: str
    side: str


@dataclass(frozen=True, slots=True)
class ModelEstimate:
    probability_target_before_stop: float
    expected_r: float
    stopout_risk: float
    regime_probability: float | None = None


@dataclass(frozen=True, slots=True)
class MetaStrategyConfig:
    probability_threshold: float
    expected_r_threshold: float
    max_stopout_risk: float
    max_symbol_exposure: float
    risk_per_trade_pct: float
    selected_threshold_source: str = "manual"


@dataclass(frozen=True, slots=True)
class RejectedTrade:
    decision_time: datetime
    symbol: str
    timeframe: str
    setup_type: str
    side: str
    reason: str
    probability_target_before_stop: float | None
    expected_r: float | None
    stopout_risk: float | None


@dataclass(frozen=True, slots=True)
class MetaStrategyReport:
    config: MetaStrategyConfig
    rule_only: BacktestReport
    ml_filtered: BacktestReport
    rejected_trades: list[RejectedTrade]
    selected_threshold_source: str

    def to_report_dict(self) -> dict[str, object]:
        return {
            "config": asdict(self.config),
            "selected_threshold_source": self.selected_threshold_source,
            "rule_only": self.rule_only.to_report_dict(),
            "ml_filtered": self.ml_filtered.to_report_dict(),
            "rejected_trade_count": len(self.rejected_trades),
            "rejected_trades": [_serialize_dataclass(trade) for trade in self.rejected_trades],
        }


def generate_trend_pullback_candidates(
    feature_rows: list[dict[str, object]],
    pullback_return_threshold: float,
    max_range_position: float,
) -> list[CandidateSetup]:
    """Generate deterministic long trend-pullback continuation candidates."""

    candidates: list[CandidateSetup] = []
    for row in sorted(feature_rows, key=lambda item: item["decision_time"]):
        close = float(row["close"])
        moving_average = _find_feature(row, "ma_")
        ma_slope = _find_feature(row, "ma_slope_")
        range_position = _find_feature(row, "range_position_")
        return_1 = float(row["return_1"])
        if (
            close > moving_average
            and ma_slope > 0
            and return_1 <= pullback_return_threshold
            and range_position <= max_range_position
        ):
            deterministic_score = round(1 - range_position, 10)
            candidates.append(
                CandidateSetup(
                    decision_time=_as_datetime(row["decision_time"]),
                    symbol=str(row["symbol"]),
                    timeframe=str(row["timeframe"]),
                    setup_type="trend_pullback_continuation",
                    side="long",
                    deterministic_score=deterministic_score,
                    rule_only_gross_r=1.0,
                )
            )
    return candidates


def evaluate_meta_strategy(
    candidates: list[CandidateSetup],
    estimates: dict[CandidateKey, ModelEstimate],
    config: MetaStrategyConfig,
) -> MetaStrategyReport:
    """Compare rule-only candidates with deterministic ML-filtered decisions."""

    _validate_config(config)
    backtest_config = BacktestConfig(
        initial_equity=10_000,
        risk_per_trade_pct=config.risk_per_trade_pct,
    )
    rule_only_report = evaluate_signal_strategy(
        "rule_only_candidates",
        [_candidate_to_signal(candidate) for candidate in candidates],
        backtest_config,
    )
    accepted_signals: list[SignalRow] = []
    rejected: list[RejectedTrade] = []
    current_symbol_exposure: dict[str, float] = {}
    for candidate in sorted(candidates, key=lambda item: item.decision_time):
        estimate = estimates.get(candidate_key(candidate))
        reason = _rejection_reason(candidate, estimate, config, current_symbol_exposure)
        if reason is not None:
            rejected.append(_rejected_trade(candidate, estimate, reason))
            continue
        current_symbol_exposure[candidate.symbol] = (
            current_symbol_exposure.get(candidate.symbol, 0.0) + config.risk_per_trade_pct
        )
        accepted_signals.append(_candidate_to_signal(candidate))

    filtered_report = evaluate_signal_strategy(
        "ml_filtered_candidates",
        accepted_signals,
        backtest_config,
    )
    return MetaStrategyReport(
        config=config,
        rule_only=rule_only_report,
        ml_filtered=filtered_report,
        rejected_trades=rejected,
        selected_threshold_source=config.selected_threshold_source,
    )


def select_threshold_on_validation(
    candidates: list[CandidateSetup],
    estimates: dict[CandidateKey, ModelEstimate],
    candidate_thresholds: tuple[float, ...],
    base_config: MetaStrategyConfig,
) -> MetaStrategyConfig:
    """Select probability threshold on validation candidates only."""

    if not candidate_thresholds:
        raise ValueError("candidate_thresholds must not be empty")
    best_threshold = candidate_thresholds[0]
    best_average_r = float("-inf")
    for threshold in candidate_thresholds:
        config = replace(
            base_config,
            probability_threshold=threshold,
            selected_threshold_source="validation",
        )
        report = evaluate_meta_strategy(candidates, estimates, config)
        average_r = report.ml_filtered.metrics.average_r
        if average_r > best_average_r:
            best_threshold = threshold
            best_average_r = average_r
    return replace(
        base_config,
        probability_threshold=best_threshold,
        selected_threshold_source="validation",
    )


def _rejection_reason(
    candidate: CandidateSetup,
    estimate: ModelEstimate | None,
    config: MetaStrategyConfig,
    symbol_exposure: dict[str, float],
) -> str | None:
    if estimate is None:
        return "missing_model_estimate"
    if estimate.probability_target_before_stop < config.probability_threshold:
        return "probability_below_threshold"
    if estimate.expected_r < config.expected_r_threshold:
        return "expected_r_below_threshold"
    if estimate.stopout_risk > config.max_stopout_risk:
        return "stopout_risk_above_limit"
    next_symbol_exposure = symbol_exposure.get(candidate.symbol, 0.0) + config.risk_per_trade_pct
    if next_symbol_exposure > config.max_symbol_exposure:
        return "symbol_exposure_cap"
    return None


def _rejected_trade(
    candidate: CandidateSetup,
    estimate: ModelEstimate | None,
    reason: str,
) -> RejectedTrade:
    return RejectedTrade(
        decision_time=candidate.decision_time,
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        setup_type=candidate.setup_type,
        side=candidate.side,
        reason=reason,
        probability_target_before_stop=estimate.probability_target_before_stop
        if estimate
        else None,
        expected_r=estimate.expected_r if estimate else None,
        stopout_risk=estimate.stopout_risk if estimate else None,
    )


def _candidate_to_signal(candidate: CandidateSetup) -> SignalRow:
    return SignalRow(
        decision_time=candidate.decision_time,
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        side=candidate.side,
        gross_r=candidate.rule_only_gross_r,
    )


def candidate_key(candidate: CandidateSetup) -> CandidateKey:
    return CandidateKey(
        decision_time=candidate.decision_time,
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        setup_type=candidate.setup_type,
        side=candidate.side,
    )


def _find_feature(row: dict[str, object], prefix: str) -> float:
    for name, value in row.items():
        if name.startswith(prefix):
            return float(value)
    raise KeyError(f"missing feature with prefix {prefix}")


def _validate_config(config: MetaStrategyConfig) -> None:
    if not 0 <= config.probability_threshold <= 1:
        raise ValueError("probability_threshold must be between 0 and 1")
    if not 0 <= config.max_stopout_risk <= 1:
        raise ValueError("max_stopout_risk must be between 0 and 1")
    if config.risk_per_trade_pct <= 0:
        raise ValueError("risk_per_trade_pct must be positive")
    if config.max_symbol_exposure <= 0:
        raise ValueError("max_symbol_exposure must be positive")


def _serialize_dataclass(value: object) -> dict[str, object]:
    payload = asdict(value)
    for key, item in payload.items():
        if isinstance(item, datetime):
            payload[key] = item.isoformat().replace("+00:00", "Z")
    return payload


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)!r}")
    return value
