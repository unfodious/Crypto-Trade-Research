"""Research-only walk-forward splits and signal evaluation."""

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_equity: float
    risk_per_trade_pct: float
    fee_r: float = 0.0
    spread_r: float = 0.0
    slippage_r: float = 0.0
    funding_r: float = 0.0
    max_trades_per_symbol: int | None = None
    max_trades_per_decision_time: int | None = None
    loss_cooldown_signals: int = 0


@dataclass(frozen=True, slots=True)
class SignalRow:
    decision_time: datetime
    symbol: str
    timeframe: str
    side: str
    gross_r: float
    confidence: float = 1.0
    exit_time: datetime | None = None

    @classmethod
    def from_iso(
        cls,
        decision_time: str,
        symbol: str,
        timeframe: str,
        side: str,
        gross_r: float,
        confidence: float = 1.0,
        exit_time: str | None = None,
    ) -> "SignalRow":
        return cls(
            decision_time=datetime.fromisoformat(decision_time.replace("Z", "+00:00")),
            symbol=symbol,
            timeframe=timeframe,
            side=side,
            gross_r=gross_r,
            confidence=confidence,
            exit_time=datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
            if exit_time
            else None,
        )


@dataclass(frozen=True, slots=True)
class TradeEvent:
    strategy_name: str
    decision_time: datetime
    exit_time: datetime
    symbol: str
    timeframe: str
    side: str
    size: float
    risk_pct: float
    gross_r: float
    fees_r: float
    spread_r: float
    slippage_r: float
    funding_r: float
    net_r: float
    pnl: float
    exit_reason: str


@dataclass(frozen=True, slots=True)
class EquityPoint:
    decision_time: datetime
    equity: float
    drawdown_pct: float


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    trade_count: int
    total_return_pct: float
    average_r: float
    expectancy_r: float
    win_rate: float
    average_win_r: float
    average_loss_r: float
    profit_factor: float
    max_drawdown_pct: float
    max_drawdown_duration: int
    exposure: float
    turnover: float
    worst_trade_r: float | None
    max_concurrent_positions: int
    max_concurrent_risk_pct: float


@dataclass(frozen=True, slots=True)
class BacktestReport:
    strategy_name: str
    config: BacktestConfig
    trades: list[TradeEvent]
    equity_curve: list[EquityPoint]
    metrics: BacktestMetrics

    def to_report_dict(self) -> dict[str, object]:
        return {
            "strategy_name": self.strategy_name,
            "config": asdict(self.config),
            "metrics": asdict(self.metrics),
            "trades": [_serialize_dataclass(trade) for trade in self.trades],
            "equity_curve": [_serialize_dataclass(point) for point in self.equity_curve],
        }


@dataclass(frozen=True, slots=True)
class WalkForwardSplit:
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime


def evaluate_signal_strategy(
    strategy_name: str,
    signals: list[SignalRow],
    config: BacktestConfig,
) -> BacktestReport:
    """Evaluate precomputed signal outcomes as research trade events."""

    _validate_config(config)
    equity = config.initial_equity
    peak_equity = equity
    trades: list[TradeEvent] = []
    equity_curve: list[EquityPoint] = []

    accepted_by_symbol: dict[str, int] = {}
    cooldown_by_symbol: dict[str, int] = {}
    for signal in _ranked_signals(signals, config):
        if signal.side == "flat" or signal.confidence <= 0:
            continue
        if signal.side not in {"long", "short"}:
            raise ValueError("signal side must be long, short, or flat")
        if _skip_for_risk_controls(
            signal,
            config,
            accepted_by_symbol,
            cooldown_by_symbol,
        ):
            continue
        exit_time = signal.exit_time or signal.decision_time
        if exit_time < signal.decision_time:
            raise ValueError("signal exit_time must be at or after decision_time")

        signal_risk_pct = config.risk_per_trade_pct * signal.confidence
        risk_amount = equity * signal_risk_pct
        net_r = signal.gross_r - _total_cost_r(config)
        pnl = risk_amount * net_r
        equity += pnl
        peak_equity = max(peak_equity, equity)
        drawdown_pct = (peak_equity - equity) / peak_equity if peak_equity else 0.0
        trade = TradeEvent(
            strategy_name=strategy_name,
            decision_time=signal.decision_time,
            exit_time=exit_time,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            side=signal.side,
            size=risk_amount,
            risk_pct=signal_risk_pct,
            gross_r=signal.gross_r,
            fees_r=-config.fee_r,
            spread_r=-config.spread_r,
            slippage_r=-config.slippage_r,
            funding_r=-config.funding_r,
            net_r=net_r,
            pnl=pnl,
            exit_reason="signal_outcome",
        )
        trades.append(trade)
        accepted_by_symbol[signal.symbol] = accepted_by_symbol.get(signal.symbol, 0) + 1
        if config.loss_cooldown_signals and net_r < 0:
            cooldown_by_symbol[signal.symbol] = config.loss_cooldown_signals
        equity_curve.append(
            EquityPoint(
                decision_time=signal.decision_time,
                equity=equity,
                drawdown_pct=drawdown_pct,
            )
        )

    return BacktestReport(
        strategy_name=strategy_name,
        config=config,
        trades=trades,
        equity_curve=equity_curve,
        metrics=_metrics(config.initial_equity, trades, equity_curve),
    )


def _ranked_signals(signals: list[SignalRow], config: BacktestConfig) -> list[SignalRow]:
    ordered = sorted(signals, key=lambda item: (item.decision_time, -item.confidence, item.symbol))
    if config.max_trades_per_decision_time is None:
        return ordered
    selected: list[SignalRow] = []
    counts_by_time: dict[datetime, int] = {}
    for signal in ordered:
        count = counts_by_time.get(signal.decision_time, 0)
        if count >= config.max_trades_per_decision_time:
            continue
        selected.append(signal)
        counts_by_time[signal.decision_time] = count + 1
    return selected


def _skip_for_risk_controls(
    signal: SignalRow,
    config: BacktestConfig,
    accepted_by_symbol: dict[str, int],
    cooldown_by_symbol: dict[str, int],
) -> bool:
    if (
        config.max_trades_per_symbol is not None
        and accepted_by_symbol.get(signal.symbol, 0) >= config.max_trades_per_symbol
    ):
        return True
    cooldown_remaining = cooldown_by_symbol.get(signal.symbol, 0)
    if cooldown_remaining > 0:
        cooldown_by_symbol[signal.symbol] = cooldown_remaining - 1
        return True
    return False


def walk_forward_splits(
    timestamps: list[datetime],
    train_size: int,
    validation_size: int,
    test_size: int,
    step_size: int,
    anchored: bool,
) -> list[WalkForwardSplit]:
    """Create rolling or anchored walk-forward splits from sorted timestamps."""

    if min(train_size, validation_size, test_size, step_size) <= 0:
        raise ValueError("split sizes must be positive")

    ordered = sorted(set(timestamps))
    total_window = train_size + validation_size + test_size
    splits: list[WalkForwardSplit] = []
    start = 0
    while start + total_window <= len(ordered):
        train_start_index = 0 if anchored else start
        train_end_index = start + train_size - 1
        validation_start_index = start + train_size
        validation_end_index = validation_start_index + validation_size - 1
        test_start_index = validation_end_index + 1
        test_end_index = test_start_index + test_size - 1
        splits.append(
            WalkForwardSplit(
                train_start=ordered[train_start_index],
                train_end=ordered[train_end_index],
                validation_start=ordered[validation_start_index],
                validation_end=ordered[validation_end_index],
                test_start=ordered[test_start_index],
                test_end=ordered[test_end_index],
            )
        )
        start += step_size
    return splits


def _metrics(
    initial_equity: float,
    trades: list[TradeEvent],
    equity_curve: list[EquityPoint],
) -> BacktestMetrics:
    net_rs = [trade.net_r for trade in trades]
    wins = [value for value in net_rs if value > 0]
    losses = [value for value in net_rs if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    final_equity = equity_curve[-1].equity if equity_curve else initial_equity
    max_concurrent_positions, max_concurrent_risk_pct = _max_concurrent_exposure(trades)
    return BacktestMetrics(
        trade_count=len(trades),
        total_return_pct=(final_equity / initial_equity) - 1,
        average_r=_mean(net_rs),
        expectancy_r=_mean(net_rs),
        win_rate=len(wins) / len(trades) if trades else 0.0,
        average_win_r=_mean(wins),
        average_loss_r=_mean(losses),
        profit_factor=gross_profit / gross_loss if gross_loss else float("inf"),
        max_drawdown_pct=max((point.drawdown_pct for point in equity_curve), default=0.0),
        max_drawdown_duration=_max_drawdown_duration(equity_curve),
        exposure=1.0 if trades else 0.0,
        turnover=sum(trade.size for trade in trades) / initial_equity if initial_equity else 0.0,
        worst_trade_r=min(net_rs) if net_rs else None,
        max_concurrent_positions=max_concurrent_positions,
        max_concurrent_risk_pct=max_concurrent_risk_pct,
    )


def _max_drawdown_duration(equity_curve: list[EquityPoint]) -> int:
    current = 0
    longest = 0
    for point in equity_curve:
        if point.drawdown_pct > 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _total_cost_r(config: BacktestConfig) -> float:
    return config.fee_r + config.spread_r + config.slippage_r + config.funding_r


def _max_concurrent_exposure(trades: list[TradeEvent]) -> tuple[int, float]:
    events: list[tuple[datetime, int, float, int]] = []
    for trade in trades:
        events.append((trade.decision_time, 1, trade.risk_pct, 1))
        exit_order = 2 if trade.exit_time == trade.decision_time else 0
        events.append((trade.exit_time, exit_order, -trade.risk_pct, -1))

    current_positions = 0
    current_risk_pct = 0.0
    max_positions = 0
    max_risk_pct = 0.0
    for _, _, risk_delta, position_delta in sorted(events):
        current_risk_pct += risk_delta
        current_positions += position_delta
        max_positions = max(max_positions, current_positions)
        max_risk_pct = max(max_risk_pct, current_risk_pct)
    return max_positions, max_risk_pct


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _validate_config(config: BacktestConfig) -> None:
    if config.initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if config.risk_per_trade_pct <= 0:
        raise ValueError("risk_per_trade_pct must be positive")
    if min(config.fee_r, config.spread_r, config.slippage_r) < 0:
        raise ValueError("costs must be non-negative")
    if config.max_trades_per_symbol is not None and config.max_trades_per_symbol <= 0:
        raise ValueError("max_trades_per_symbol must be positive when set")
    if config.max_trades_per_decision_time is not None and config.max_trades_per_decision_time <= 0:
        raise ValueError("max_trades_per_decision_time must be positive when set")
    if config.loss_cooldown_signals < 0:
        raise ValueError("loss_cooldown_signals must be non-negative")


def _serialize_dataclass(value: object) -> dict[str, object]:
    payload = asdict(value)
    for key, item in payload.items():
        if isinstance(item, datetime):
            payload[key] = item.isoformat().replace("+00:00", "Z")
    return payload
