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
    exit_model: str = "fixed_target_stop"
    breakeven_activation_r: float | None = None
    breakeven_lock_r: float = 0.0
    trailing_stop_r: float | None = None


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
    label_rows: list[dict[str, object]] = []
    for group_rows in _group_rows(sorted_rows):
        label_rows.extend(
            _build_label_row(group_rows, index, config) for index in range(len(group_rows))
        )
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


def generate_trade_labels_for_keys(
    rows: Sequence[dict[str, object]],
    config: LabelConfig,
    include_keys: set[tuple[object, ...]],
) -> LabelFrame:
    """Generate trade labels only for requested market-row keys."""

    _validate_config(config)
    if not include_keys:
        return LabelFrame(
            rows=[],
            manifest=LabelManifest(
                schema_version=SCHEMA_VERSION,
                label_set_version=config.label_set_version,
                generator_name=GENERATOR_NAME,
                row_count=0,
                horizon_bars=config.horizon_bars,
                side=config.side,
                labels=_label_specs(config.horizon_bars),
            ),
        )

    sorted_rows = sorted(rows, key=_sort_key)
    label_rows: list[dict[str, object]] = []
    for group_rows in _group_rows(sorted_rows):
        for index, row in enumerate(group_rows):
            if _row_label_key(row) in include_keys:
                label_rows.append(_build_label_row(group_rows, index, config))
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
    mfe_r = _mfe_r(future_rows, config.side, entry_price, risk_per_unit)
    mae_r = _mae_r(future_rows, config.side, entry_price, risk_per_unit)
    outcome = _label_outcome(
        future_rows=future_rows,
        config=config,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        risk_per_unit=risk_per_unit,
        forward_return=forward_return,
    )
    directional_class = _directional_class(forward_return, config)
    no_trade_reason = "below_cost_or_noise_threshold" if directional_class == "flat" else None

    return {
        **base,
        "forward_return": forward_return,
        "directional_class": directional_class,
        "target_before_stop": outcome["target_before_stop"],
        "realized_r_after_costs": outcome["realized_r_after_costs"],
        "max_favorable_excursion_r": mfe_r,
        "max_adverse_excursion_r": mae_r,
        "time_to_target_bars": outcome["time_to_target_bars"],
        "time_to_stop_bars": outcome["time_to_stop_bars"],
        "time_to_breakeven_bars": outcome["time_to_breakeven_bars"],
        "dynamic_exit_reason": outcome["dynamic_exit_reason"],
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
        ("time_to_breakeven_bars", "duration", "Bars until dynamic stop first moved up."),
        ("dynamic_exit_reason", "classification", "Dynamic exit reason when configured."),
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
    if config.exit_model not in {"fixed_target_stop", "breakeven_trailing"}:
        raise ValueError("exit_model must be fixed_target_stop or breakeven_trailing")
    if config.breakeven_activation_r is not None and config.breakeven_activation_r <= 0:
        raise ValueError("breakeven_activation_r must be positive when set")
    if config.breakeven_lock_r < 0:
        raise ValueError("breakeven_lock_r must be non-negative")
    if config.trailing_stop_r is not None and config.trailing_stop_r <= 0:
        raise ValueError("trailing_stop_r must be positive when set")
    if (
        config.exit_model == "breakeven_trailing"
        and config.breakeven_activation_r is None
        and config.trailing_stop_r is None
    ):
        raise ValueError("breakeven_trailing requires breakeven_activation_r or trailing_stop_r")


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


def _label_outcome(
    *,
    future_rows: Sequence[dict[str, object]],
    config: LabelConfig,
    entry_price: float,
    stop_price: float,
    target_price: float,
    risk_per_unit: float,
    forward_return: float,
) -> dict[str, object]:
    if config.exit_model == "fixed_target_stop":
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
        realized_r = _realized_r_after_costs(
            target_before_stop=target_before_stop,
            forward_return=forward_return,
            risk_pct=config.stop_loss_pct,
            cost_pct=config.cost_pct,
            target_pct=config.target_pct,
        )
        return {
            "target_before_stop": target_before_stop,
            "realized_r_after_costs": realized_r,
            "time_to_target_bars": time_to_target,
            "time_to_stop_bars": time_to_stop,
            "time_to_breakeven_bars": None,
            "dynamic_exit_reason": None,
        }

    realized_r, time_to_stop, time_to_breakeven, exit_reason = _breakeven_trailing_outcome(
        future_rows,
        config,
        entry_price,
        stop_price,
        risk_per_unit,
    )
    return {
        "target_before_stop": realized_r > 0,
        "realized_r_after_costs": realized_r,
        "time_to_target_bars": None,
        "time_to_stop_bars": time_to_stop,
        "time_to_breakeven_bars": time_to_breakeven,
        "dynamic_exit_reason": exit_reason,
    }


def _breakeven_trailing_outcome(
    future_rows: Sequence[dict[str, object]],
    config: LabelConfig,
    entry_price: float,
    initial_stop_price: float,
    risk_per_unit: float,
) -> tuple[float, int | None, int | None, str]:
    stop_price = initial_stop_price
    time_to_breakeven = None
    cost_r = config.cost_pct / config.stop_loss_pct
    for offset, row in enumerate(future_rows, start=1):
        high = _as_float(row["high"])
        low = _as_float(row["low"])
        if _stop_hit(config.side, high, low, stop_price):
            return (
                _price_r(stop_price, entry_price, config.side, risk_per_unit) - cost_r,
                offset,
                time_to_breakeven,
                "dynamic_stop",
            )

        next_stop = stop_price
        favorable_price = high if config.side == "long" else low
        favorable_r = _price_r(favorable_price, entry_price, config.side, risk_per_unit)
        if (
            config.breakeven_activation_r is not None
            and favorable_r >= config.breakeven_activation_r
        ):
            if time_to_breakeven is None:
                time_to_breakeven = offset
            lock_stop = _price_at_r(
                entry_price,
                config.side,
                risk_per_unit,
                config.breakeven_lock_r,
            )
            next_stop = _more_protective_stop(config.side, next_stop, lock_stop)
        if config.trailing_stop_r is not None and favorable_r >= config.trailing_stop_r:
            trail_stop = _trailing_stop_price(
                favorable_price,
                config.side,
                risk_per_unit,
                config.trailing_stop_r,
            )
            next_stop = _more_protective_stop(config.side, next_stop, trail_stop)

        if next_stop != stop_price and _stop_hit(config.side, high, low, next_stop):
            stop_price = next_stop
            if config.target_stop_tie_breaker == "stop_first":
                return (
                    _price_r(stop_price, entry_price, config.side, risk_per_unit) - cost_r,
                    offset,
                    time_to_breakeven,
                    "dynamic_stop",
                )
        stop_price = next_stop

    close = _as_float(future_rows[-1]["close"])
    return (
        _price_r(close, entry_price, config.side, risk_per_unit) - cost_r,
        None,
        time_to_breakeven,
        "horizon_exit",
    )


def _stop_hit(side: str, high: float, low: float, stop_price: float) -> bool:
    if side == "long":
        return low <= stop_price
    return high >= stop_price


def _price_r(price: float, entry_price: float, side: str, risk_per_unit: float) -> float:
    if side == "long":
        return (price - entry_price) / risk_per_unit
    return (entry_price - price) / risk_per_unit


def _price_at_r(entry_price: float, side: str, risk_per_unit: float, r_multiple: float) -> float:
    if side == "long":
        return entry_price + r_multiple * risk_per_unit
    return entry_price - r_multiple * risk_per_unit


def _trailing_stop_price(
    favorable_price: float,
    side: str,
    risk_per_unit: float,
    trailing_stop_r: float,
) -> float:
    if side == "long":
        return favorable_price - trailing_stop_r * risk_per_unit
    return favorable_price + trailing_stop_r * risk_per_unit


def _more_protective_stop(side: str, current_stop: float, candidate_stop: float) -> float:
    if side == "long":
        return max(current_stop, candidate_stop)
    return min(current_stop, candidate_stop)


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


def _group_rows(rows: Sequence[dict[str, object]]) -> list[list[dict[str, object]]]:
    groups: list[list[dict[str, object]]] = []
    for row in rows:
        if not groups or _group_key(groups[-1][0]) != _group_key(row):
            groups.append([])
        groups[-1].append(row)
    return groups


def _group_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
    )


def _row_label_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        _as_datetime(row["close_time"]),
    )


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)!r}")
    return value


def _as_float(value: object) -> float:
    return float(value)
