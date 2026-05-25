"""Simple non-neural baselines for supervised trading research."""

import math
from dataclasses import asdict, dataclass
from datetime import datetime

from crypto_trade_research.backtest import (
    BacktestConfig,
    BacktestReport,
    SignalRow,
    evaluate_signal_strategy,
)


@dataclass(frozen=True, slots=True)
class ModelSample:
    decision_time: datetime
    symbol: str
    timeframe: str
    side: str
    features: dict[str, float]
    target_before_stop: bool
    realized_r_after_costs: float

    @classmethod
    def from_iso(
        cls,
        decision_time: str,
        setup_score: float,
        realized_r_after_costs: float,
        side: str = "long",
    ) -> "ModelSample":
        return cls(
            decision_time=datetime.fromisoformat(decision_time.replace("Z", "+00:00")),
            symbol="BTCUSDT",
            timeframe="1d",
            side=side,
            features={"setup_score": setup_score, "noise": 1.0 - setup_score},
            target_before_stop=realized_r_after_costs > 0,
            realized_r_after_costs=realized_r_after_costs,
        )


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    feature_names: tuple[str, ...]
    decision_feature: str
    train_end: datetime
    validation_end: datetime
    test_end: datetime
    probability_threshold: float = 0.5
    initial_equity: float = 10_000
    risk_per_trade_pct: float = 0.01


@dataclass(frozen=True, slots=True)
class TimeSplit:
    name: str
    start: datetime
    end: datetime
    row_count: int


@dataclass(frozen=True, slots=True)
class BaselineComparisonReport:
    splits: list[TimeSplit]
    model_metadata: dict[str, object]
    feature_importance: list[dict[str, float | str]]
    strategy_reports: dict[str, BacktestReport]
    decision: str
    rejection_reason: str | None

    def to_report_dict(self) -> dict[str, object]:
        return {
            "splits": [_serialize_dataclass(split) for split in self.splits],
            "model_metadata": self.model_metadata,
            "feature_importance": self.feature_importance,
            "decision": self.decision,
            "rejection_reason": self.rejection_reason,
            "strategies": {
                name: report.to_report_dict() for name, report in self.strategy_reports.items()
            },
        }


@dataclass(frozen=True, slots=True)
class LinearProbabilityModel:
    feature_name: str
    threshold: float
    positive_direction: int

    def probability(self, sample: ModelSample) -> float:
        value = sample.features[self.feature_name]
        margin = value - self.threshold if self.positive_direction >= 0 else self.threshold - value
        return 1 / (1 + math.exp(-10 * margin))


def train_and_evaluate_baselines(
    samples: list[ModelSample],
    config: BaselineConfig,
) -> BaselineComparisonReport:
    """Train simple baselines and evaluate them through the CT-40 backtest layer."""

    _validate_config(config)
    ordered = sorted(samples, key=lambda sample: sample.decision_time)
    train_samples = [sample for sample in ordered if sample.decision_time <= config.train_end]
    validation_samples = [
        sample
        for sample in ordered
        if config.train_end < sample.decision_time <= config.validation_end
    ]
    test_samples = [
        sample
        for sample in ordered
        if config.validation_end < sample.decision_time <= config.test_end
    ]
    model = _fit_linear_probability_model(train_samples, config.decision_feature)
    all_samples = train_samples + validation_samples + test_samples

    backtest_config = BacktestConfig(
        initial_equity=config.initial_equity,
        risk_per_trade_pct=config.risk_per_trade_pct,
    )
    strategy_reports = {
        "no_trade": evaluate_signal_strategy("no_trade", [], backtest_config),
        "rule_only": evaluate_signal_strategy(
            "rule_only",
            [_sample_to_signal(sample) for sample in all_samples],
            backtest_config,
        ),
        "linear_probability": evaluate_signal_strategy(
            "linear_probability",
            [
                _sample_to_signal(sample)
                for sample in all_samples
                if model.probability(sample) >= config.probability_threshold
            ],
            backtest_config,
        ),
    }
    validation_test_samples = validation_samples + test_samples
    validation_test_model_report = evaluate_signal_strategy(
        "linear_probability_oos",
        [
            _sample_to_signal(sample)
            for sample in validation_test_samples
            if model.probability(sample) >= config.probability_threshold
        ],
        backtest_config,
    )
    decision = "research_further"
    rejection_reason = None
    if validation_test_model_report.metrics.average_r <= 0:
        decision = "reject"
        rejection_reason = "model edge failed outside the training window"

    return BaselineComparisonReport(
        splits=_splits(train_samples, validation_samples, test_samples, config),
        model_metadata={
            "model_type": "linear_probability_threshold",
            "feature_names": list(config.feature_names),
            "decision_feature": config.decision_feature,
            "probability_threshold": config.probability_threshold,
            "train_window": [
                _format_timestamp(train_samples[0].decision_time),
                _format_timestamp(config.train_end),
            ],
            "validation_window": [
                _format_timestamp(config.train_end),
                _format_timestamp(config.validation_end),
            ],
            "test_window": [
                _format_timestamp(config.validation_end),
                _format_timestamp(config.test_end),
            ],
            "oos_average_r": validation_test_model_report.metrics.average_r,
            "oos_trade_count": validation_test_model_report.metrics.trade_count,
        },
        feature_importance=[
            {
                "feature": model.feature_name,
                "importance": 1.0,
            }
        ],
        strategy_reports=strategy_reports,
        decision=decision,
        rejection_reason=rejection_reason,
    )


def _fit_linear_probability_model(
    samples: list[ModelSample],
    feature_name: str,
) -> LinearProbabilityModel:
    if not samples:
        raise ValueError("training split must not be empty")

    winners = [sample.features[feature_name] for sample in samples if sample.target_before_stop]
    losers = [sample.features[feature_name] for sample in samples if not sample.target_before_stop]
    if not winners or not losers:
        values = [sample.features[feature_name] for sample in samples]
        return LinearProbabilityModel(feature_name, sum(values) / len(values), 1)

    winner_mean = sum(winners) / len(winners)
    loser_mean = sum(losers) / len(losers)
    return LinearProbabilityModel(
        feature_name=feature_name,
        threshold=(winner_mean + loser_mean) / 2,
        positive_direction=1 if winner_mean >= loser_mean else -1,
    )


def _sample_to_signal(sample: ModelSample) -> SignalRow:
    return SignalRow(
        decision_time=sample.decision_time,
        symbol=sample.symbol,
        timeframe=sample.timeframe,
        side=sample.side,
        gross_r=sample.realized_r_after_costs,
    )


def _splits(
    train_samples: list[ModelSample],
    validation_samples: list[ModelSample],
    test_samples: list[ModelSample],
    config: BaselineConfig,
) -> list[TimeSplit]:
    return [
        TimeSplit(
            "train",
            train_samples[0].decision_time if train_samples else config.train_end,
            config.train_end,
            len(train_samples),
        ),
        TimeSplit(
            "validation",
            validation_samples[0].decision_time if validation_samples else config.train_end,
            config.validation_end,
            len(validation_samples),
        ),
        TimeSplit(
            "test",
            test_samples[0].decision_time if test_samples else config.validation_end,
            config.test_end,
            len(test_samples),
        ),
    ]


def _validate_config(config: BaselineConfig) -> None:
    if not config.feature_names:
        raise ValueError("feature_names must not be empty")
    if config.decision_feature not in config.feature_names:
        raise ValueError("decision_feature must be listed in feature_names")
    if not (config.train_end <= config.validation_end <= config.test_end):
        raise ValueError("train_end, validation_end, and test_end must be time ordered")
    if not 0 <= config.probability_threshold <= 1:
        raise ValueError("probability_threshold must be between 0 and 1")


def _serialize_dataclass(value: object) -> dict[str, object]:
    payload = asdict(value)
    for key, item in payload.items():
        if isinstance(item, datetime):
            payload[key] = _format_timestamp(item)
    return payload


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
