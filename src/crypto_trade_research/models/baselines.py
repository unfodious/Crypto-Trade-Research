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
    ridge_lambda: float = 1.0


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
                name: _strategy_report_dict(name, report)
                for name, report in self.strategy_reports.items()
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


@dataclass(frozen=True, slots=True)
class RidgeProbabilityModel:
    feature_names: tuple[str, ...]
    means: dict[str, float]
    standard_deviations: dict[str, float]
    intercept: float
    weights: dict[str, float]

    def probability(self, sample: ModelSample) -> float:
        score = self.intercept
        for feature_name in self.feature_names:
            value = sample.features.get(feature_name, self.means[feature_name])
            standard_deviation = self.standard_deviations[feature_name]
            standardized = (
                0.0
                if standard_deviation == 0
                else (value - self.means[feature_name]) / standard_deviation
            )
            score += self.weights[feature_name] * standardized
        return 1 / (1 + math.exp(-score))


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
    ridge_model = _fit_ridge_probability_model(train_samples, config)
    all_samples = train_samples + validation_samples + test_samples

    backtest_config = BacktestConfig(
        initial_equity=config.initial_equity,
        risk_per_trade_pct=config.risk_per_trade_pct,
    )
    validation_test_samples = validation_samples + test_samples
    ridge_probability_threshold = _calibrate_probability_threshold(
        ridge_model,
        validation_samples,
        backtest_config,
        fallback=config.probability_threshold,
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
        "multifeature_ridge": evaluate_signal_strategy(
            "multifeature_ridge",
            [
                _sample_to_signal(sample)
                for sample in all_samples
                if ridge_model.probability(sample) >= ridge_probability_threshold
            ],
            backtest_config,
        ),
        "no_trade_oos": evaluate_signal_strategy("no_trade_oos", [], backtest_config),
        "rule_only_oos": evaluate_signal_strategy(
            "rule_only_oos",
            [_sample_to_signal(sample) for sample in validation_test_samples],
            backtest_config,
        ),
        "linear_probability_oos": evaluate_signal_strategy(
            "linear_probability_oos",
            [
                _sample_to_signal(sample)
                for sample in validation_test_samples
                if model.probability(sample) >= config.probability_threshold
            ],
            backtest_config,
        ),
        "multifeature_ridge_oos": evaluate_signal_strategy(
            "multifeature_ridge_oos",
            [
                _sample_to_signal(sample)
                for sample in validation_test_samples
                if ridge_model.probability(sample) >= ridge_probability_threshold
            ],
            backtest_config,
        ),
    }
    validation_test_model_report = strategy_reports["multifeature_ridge_oos"]
    decision = "research_further"
    rejection_reason = None
    if validation_test_model_report.metrics.average_r <= 0:
        decision = "reject"
        rejection_reason = "model edge failed outside the training window"

    return BaselineComparisonReport(
        splits=_splits(train_samples, validation_samples, test_samples, config),
        model_metadata={
            "model_type": "linear_probability_threshold",
            "multifeature_model_type": "ridge_probability",
            "feature_names": list(config.feature_names),
            "decision_feature": config.decision_feature,
            "probability_threshold": config.probability_threshold,
            "multifeature_probability_threshold": ridge_probability_threshold,
            "multifeature_feature_count": len(ridge_model.feature_names),
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
        ]
        + _ridge_feature_importance(ridge_model),
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


def _fit_ridge_probability_model(
    samples: list[ModelSample],
    config: BaselineConfig,
) -> RidgeProbabilityModel:
    if not samples:
        raise ValueError("training split must not be empty")
    feature_names = tuple(
        name for name in config.feature_names if any(name in sample.features for sample in samples)
    )
    if not feature_names:
        raise ValueError("multifeature model requires at least one populated feature")

    means = {
        name: _mean([sample.features[name] for sample in samples if name in sample.features])
        for name in feature_names
    }
    standard_deviations = {
        name: _standard_deviation([sample.features.get(name, means[name]) for sample in samples])
        for name in feature_names
    }
    matrix = [
        [1.0]
        + [
            _standardized(
                sample.features.get(name, means[name]),
                means[name],
                standard_deviations[name],
            )
            for name in feature_names
        ]
        for sample in samples
    ]
    targets = [1.0 if sample.target_before_stop else 0.0 for sample in samples]
    coefficients = _solve_ridge(matrix, targets, config.ridge_lambda)
    return RidgeProbabilityModel(
        feature_names=feature_names,
        means=means,
        standard_deviations=standard_deviations,
        intercept=coefficients[0],
        weights={
            name: coefficient
            for name, coefficient in zip(feature_names, coefficients[1:], strict=False)
        },
    )


def fit_ridge_probability_model(
    samples: list[ModelSample],
    config: BaselineConfig,
) -> RidgeProbabilityModel:
    """Fit the dependency-free multifeature ridge-probability baseline."""

    return _fit_ridge_probability_model(samples, config)


def _calibrate_probability_threshold(
    model: RidgeProbabilityModel,
    validation_samples: list[ModelSample],
    backtest_config: BacktestConfig,
    *,
    fallback: float,
) -> float:
    if not validation_samples:
        return fallback
    candidates = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
    scored: list[tuple[float, int, float]] = []
    for threshold in candidates:
        report = evaluate_signal_strategy(
            "validation_threshold",
            [
                _sample_to_signal(sample)
                for sample in validation_samples
                if model.probability(sample) >= threshold
            ],
            backtest_config,
        )
        scored.append((report.metrics.average_r, report.metrics.trade_count, threshold))
    best_average_r, best_trade_count, best_threshold = max(
        scored,
        key=lambda item: (item[0], item[1], item[2]),
    )
    if best_trade_count == 0 or math.isnan(best_average_r):
        return fallback
    return best_threshold


def _ridge_feature_importance(model: RidgeProbabilityModel) -> list[dict[str, float | str]]:
    return [
        {
            "feature": feature_name,
            "importance": abs(weight),
            "model": "multifeature_ridge",
        }
        for feature_name, weight in sorted(
            model.weights.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:20]
    ]


def _solve_ridge(
    matrix: list[list[float]],
    targets: list[float],
    ridge_lambda: float,
) -> list[float]:
    column_count = len(matrix[0])
    xtx = [[0.0 for _ in range(column_count)] for _ in range(column_count)]
    xty = [0.0 for _ in range(column_count)]
    for row, target in zip(matrix, targets, strict=False):
        for left_index in range(column_count):
            xty[left_index] += row[left_index] * target
            for right_index in range(column_count):
                xtx[left_index][right_index] += row[left_index] * row[right_index]
    for index in range(1, column_count):
        xtx[index][index] += ridge_lambda
    return _solve_linear_system(xtx, xty)


def _solve_linear_system(matrix: list[list[float]], values: list[float]) -> list[float]:
    size = len(values)
    augmented = [row[:] + [value] for row, value in zip(matrix, values, strict=False)]
    for pivot_index in range(size):
        pivot_row = max(
            range(pivot_index, size),
            key=lambda row_index: abs(augmented[row_index][pivot_index]),
        )
        if abs(augmented[pivot_row][pivot_index]) < 1e-12:
            augmented[pivot_index][pivot_index] = 1e-12
        else:
            augmented[pivot_index], augmented[pivot_row] = (
                augmented[pivot_row],
                augmented[pivot_index],
            )
        pivot = augmented[pivot_index][pivot_index]
        augmented[pivot_index] = [value / pivot for value in augmented[pivot_index]]
        for row_index in range(size):
            if row_index == pivot_index:
                continue
            factor = augmented[row_index][pivot_index]
            augmented[row_index] = [
                current - factor * pivot_value
                for current, pivot_value in zip(
                    augmented[row_index],
                    augmented[pivot_index],
                    strict=False,
                )
            ]
    return [row[-1] for row in augmented]


def _standardized(value: float, mean_value: float, standard_deviation: float) -> float:
    if standard_deviation == 0:
        return 0.0
    return (value - mean_value) / standard_deviation


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _standard_deviation(values: list[float]) -> float:
    mean_value = _mean(values)
    variance = _mean([(value - mean_value) ** 2 for value in values])
    return math.sqrt(variance)


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


def _strategy_report_dict(name: str, report: BacktestReport) -> dict[str, object]:
    payload = report.to_report_dict()
    payload["sample_scope"] = (
        "validation_test" if name.endswith("_oos") else "train_validation_test"
    )
    return payload


def _format_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
