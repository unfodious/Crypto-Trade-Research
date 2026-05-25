"""After-the-fact supervised labels for trade outcome research."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

SCHEMA_VERSION = "research.dataset.v1"
GENERATOR_NAME = "crypto_trade_research.trade_outcome_labels"


@dataclass(frozen=True, slots=True)
class LabelConfig:
    label_set_version: str
    horizon_bars: int
    side: str
    stop_loss_pct: float
    target_pct: float
    cost_pct: float
    flat_threshold_pct: float
    target_stop_tie_breaker: str = "stop_first"


@dataclass(frozen=True, slots=True)
class LabelSpec:
    name: str
    label_type: str
    horizon_bars: int
    availability: str
    description: str


@dataclass(frozen=True, slots=True)
class LabelManifest:
    schema_version: str
    label_set_version: str
    generator_name: str
    row_count: int
    horizon_bars: int
    side: str
    labels: tuple[LabelSpec, ...]


@dataclass(frozen=True, slots=True)
class LabelFrame:
    rows: list[dict[str, object]]
    manifest: LabelManifest


def generate_trade_labels(
    rows: Sequence[dict[str, object]],
    config: LabelConfig,
) -> LabelFrame:
    """Generate after-the-fact trade labels from future OHLC windows."""

    _validate_config(config)
    sorted_rows = sorted(rows, key=_sort_key)
    label_rows = [_build_label_row(sorted_rows, index, config) for index in range(len(sorted_rows))]
    return LabelFrame(
        rows=label_rows,
        manifest=LabelManifest(
            schema_version=SCHEMA_VERSION,
            label_set_version=config.label_set_version,
            generator_name=GENERATOR_NAME,
            row_count=len(label_rows),
            horizon_bars=config.horizon_bars,
            side=config.side,
            labels=_label_specs(config.horizon_bars),
        ),
    )


def _build_label_row(
    rows: Sequence[dict[str, object]],
    index: int,
    config: LabelConfig,
) -> dict[str, object]:
    row = rows[index]
    future_rows = rows[index + 1 : index + 1 + config.horizon_bars]
    entry_price = _as_float(row["close"])
    stop_price, target_price = _stop_and_target(entry_price, config)
    risk_per_unit = abs(entry_price - stop_price)

    base = {
        "schema_version": SCHEMA_VERSION,
        "label_set_version": config.label_set_version,
        "venue": row["venue"],
        "market_type": row["market_type"],
        "symbol": row["symbol"],
        "timeframe": row["timeframe"],
        "decision_time": _as_datetime(row["close_time"]),
        "side": config.side,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "risk_per_unit": risk_per_unit,
        "source_window_start": _as_datetime(future_rows[0]["close_time"]) if future_rows else None,
        "source_window_end": _as_datetime(future_rows[-1]["close_time"]) if future_rows else None,
    }

    if len(future_rows) < config.horizon_bars:
        return {
            **base,
            "forward_return": None,
            "directional_class": "no_trade",
            "target_before_stop": None,
            "realized_r_after_costs": None,
            "max_favorable_excursion_r": None,
            "max_adverse_excursion_r": None,
            "time_to_target_bars": None,
            "time_to_stop_bars": None,
            "no_trade_reason": "insufficient_future_window",
        }

    forward_return = _forward_return(entry_price, _as_float(future_rows[-1]["close"]), config.side)
    time_to_target, time_to_stop = _target_stop_times(
        future_rows,
        config.side,
        stop_price,
        target_price,
    )
    target_before_stop = _target_before_stop(
        time_to_target,
        time_to_stop,
        config.target_stop_tie_breaker,
    )
    mfe_r = _mfe_r(future_rows, config.side, entry_price, risk_per_unit)
    mae_r = _mae_r(future_rows, config.side, entry_price, risk_per_unit)
    realized_r = _realized_r_after_costs(
        target_before_stop=target_before_stop,
        forward_return=forward_return,
        risk_pct=config.stop_loss_pct,
        cost_pct=config.cost_pct,
        target_pct=config.target_pct,
    )
    directional_class = _directional_class(forward_return, config)
    no_trade_reason = "below_cost_or_noise_threshold" if directional_class == "flat" else None

    return {
        **base,
        "forward_return": forward_return,
        "directional_class": directional_class,
        "target_before_stop": target_before_stop,
        "realized_r_after_costs": realized_r,
        "max_favorable_excursion_r": mfe_r,
        "max_adverse_excursion_r": mae_r,
        "time_to_target_bars": time_to_target,
        "time_to_stop_bars": time_to_stop,
        "no_trade_reason": no_trade_reason,
    }


def _label_specs(horizon_bars: int) -> tuple[LabelSpec, ...]:
    labels = [
        ("forward_return", "regression", "Forward return over the configured horizon."),
        ("directional_class", "classification", "Up/down/flat/no-trade after cost threshold."),
        ("target_before_stop", "classification", "Whether target was hit before stop."),
        ("realized_r_after_costs", "regression", "Outcome in R multiples after costs."),
        ("max_favorable_excursion_r", "regression", "Best favorable move in R."),
        ("max_adverse_excursion_r", "regression", "Worst adverse move in R."),
        ("time_to_target_bars", "duration", "Bars until target hit."),
        ("time_to_stop_bars", "duration", "Bars until stop hit."),
        ("no_trade_reason", "classification", "Reason label should be excluded or neutral."),
    ]
    return tuple(
        LabelSpec(name, label_type, horizon_bars, "after_the_fact", description)
        for name, label_type, description in labels
    )


def _validate_config(config: LabelConfig) -> None:
    if config.horizon_bars <= 0:
        raise ValueError("horizon_bars must be positive")
    if config.side not in {"long", "short"}:
        raise ValueError("side must be long or short")
    if config.stop_loss_pct <= 0:
        raise ValueError("stop_loss_pct must be positive")
    if config.target_pct <= 0:
        raise ValueError("target_pct must be positive")
    if config.cost_pct < 0:
        raise ValueError("cost_pct must be non-negative")
    if config.flat_threshold_pct < 0:
        raise ValueError("flat_threshold_pct must be non-negative")
    if config.target_stop_tie_breaker not in {"stop_first", "target_first"}:
        raise ValueError("target_stop_tie_breaker must be stop_first or target_first")


def _stop_and_target(entry_price: float, config: LabelConfig) -> tuple[float, float]:
    if config.side == "long":
        return entry_price * (1 - config.stop_loss_pct), entry_price * (1 + config.target_pct)
    return entry_price * (1 + config.stop_loss_pct), entry_price * (1 - config.target_pct)


def _target_stop_times(
    future_rows: Sequence[dict[str, object]],
    side: str,
    stop_price: float,
    target_price: float,
) -> tuple[int | None, int | None]:
    time_to_target = None
    time_to_stop = None
    for offset, row in enumerate(future_rows, start=1):
        high = _as_float(row["high"])
        low = _as_float(row["low"])
        if side == "long":
            target_hit = high >= target_price
            stop_hit = low <= stop_price
        else:
            target_hit = low <= target_price
            stop_hit = high >= stop_price
        if target_hit and time_to_target is None:
            time_to_target = offset
        if stop_hit and time_to_stop is None:
            time_to_stop = offset
    return time_to_target, time_to_stop


def _target_before_stop(
    time_to_target: int | None,
    time_to_stop: int | None,
    tie_breaker: str,
) -> bool | None:
    if time_to_target is None and time_to_stop is None:
        return None
    if time_to_target is None:
        return False
    if time_to_stop is None:
        return True
    if time_to_target == time_to_stop:
        return tie_breaker == "target_first"
    return time_to_target < time_to_stop


def _mfe_r(
    future_rows: Sequence[dict[str, object]],
    side: str,
    entry_price: float,
    risk_per_unit: float,
) -> float:
    if side == "long":
        best_price = max(_as_float(row["high"]) for row in future_rows)
        return (best_price - entry_price) / risk_per_unit
    best_price = min(_as_float(row["low"]) for row in future_rows)
    return (entry_price - best_price) / risk_per_unit


def _mae_r(
    future_rows: Sequence[dict[str, object]],
    side: str,
    entry_price: float,
    risk_per_unit: float,
) -> float:
    if side == "long":
        worst_price = min(_as_float(row["low"]) for row in future_rows)
        return (worst_price - entry_price) / risk_per_unit
    worst_price = max(_as_float(row["high"]) for row in future_rows)
    return (entry_price - worst_price) / risk_per_unit


def _realized_r_after_costs(
    target_before_stop: bool | None,
    forward_return: float,
    risk_pct: float,
    cost_pct: float,
    target_pct: float,
) -> float:
    cost_r = cost_pct / risk_pct
    if target_before_stop is True:
        return target_pct / risk_pct - cost_r
    if target_before_stop is False:
        return -1 - cost_r
    return forward_return / risk_pct - cost_r


def _forward_return(entry_price: float, exit_price: float, side: str) -> float:
    if side == "long":
        return exit_price / entry_price - 1
    return entry_price / exit_price - 1


def _directional_class(forward_return: float, config: LabelConfig) -> str:
    threshold = config.cost_pct + config.flat_threshold_pct
    if abs(forward_return) <= threshold:
        return "flat"
    return "up" if forward_return > 0 else "down"


def _sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        row["close_time"],
    )


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)!r}")
    return value


def _as_float(value: object) -> float:
    return float(value)
