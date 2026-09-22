"""Portfolio economics for a set of labelled trades.

Sizing is fixed-fractional on the stop distance: risk `risk_fraction` of equity
per trade, so notional = risk / stop_distance, capped at `max_leverage`. This is
deliberately not the audit's "100 USDT margin, fixed leverage" scheme - that one
made position size a function of leverage rather than of risk, which is how
`middle-indicators` ended up with a 100%-of-margin loss tail.

Costs come from `CostModel` and are charged on notional, so a wide stop (small
notional for the same risk) pays less. This is exactly the arithmetic the audit
identified as decisive, made explicit.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from crypto_trade_research.edge_study.costs import CostModel

BARS_PER_YEAR_4H = 6 * 365


@dataclass(frozen=True)
class PortfolioConfig:
    initial_equity: float = 10_000.0
    risk_fraction: float = 0.01
    max_leverage: float = 3.0
    one_position_per_pair: bool = True


DEFAULT_PORTFOLIO = PortfolioConfig()


@dataclass(frozen=True)
class Metrics:
    trades: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    profit_factor: float
    expectancy_r: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe: float
    sortino: float
    exposure: float
    cost_drag_return: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _drop_overlaps(trades: pd.DataFrame) -> pd.DataFrame:
    """Keep at most one open position per pair at a time."""
    kept: list[int] = []
    last_exit: dict[str, pd.Timestamp] = {}
    for position, trade in enumerate(trades.itertuples(index=False)):
        previous = last_exit.get(trade.pair)
        if previous is not None and trade.decision_time < previous:
            continue
        kept.append(position)
        last_exit[trade.pair] = trade.exit_time
    return trades.iloc[kept]


def simulate(
    trades: pd.DataFrame,
    costs: CostModel,
    config: PortfolioConfig | None = None,
) -> tuple[Metrics, pd.DataFrame, pd.Series]:
    """Run the trade list through the portfolio and return metrics + equity."""
    config = config or DEFAULT_PORTFOLIO
    if trades.empty:
        empty = pd.Series(dtype=float)
        return _empty_metrics(), trades, empty

    trades = trades.sort_values("decision_time").reset_index(drop=True)
    if config.one_position_per_pair:
        trades = _drop_overlaps(trades).reset_index(drop=True)
    if trades.empty:
        return _empty_metrics(), trades, pd.Series(dtype=float)

    stop_fraction = (trades["risk_per_unit"] / trades["entry_price"]).to_numpy(dtype=float)
    notional_fraction = np.minimum(config.risk_fraction / stop_fraction, config.max_leverage)
    effective_risk = notional_fraction * stop_fraction

    funding = np.array(
        [
            costs.funding_cost(int(side), float(hours))
            for side, hours in zip(trades["side"], trades["hours_held"], strict=True)
        ]
    )
    cost_fraction = notional_fraction * (costs.round_trip + funding)
    gross_fraction = trades["gross_r"].to_numpy(dtype=float) * effective_risk
    net_fraction = gross_fraction - cost_fraction

    result = trades.copy()
    result["notional_fraction"] = notional_fraction
    result["effective_risk"] = effective_risk
    result["cost_fraction"] = cost_fraction
    result["gross_fraction"] = gross_fraction
    result["net_fraction"] = net_fraction
    result["net_r"] = np.where(effective_risk > 0, net_fraction / effective_risk, 0.0)

    equity, equity_curve = _run_equity(result, config.initial_equity)
    result["equity_after"] = equity

    metrics = _metrics(result, equity_curve, config.initial_equity, costs)
    return metrics, result, equity_curve


def _run_equity(trades: pd.DataFrame, initial_equity: float) -> tuple[np.ndarray, pd.Series]:
    """Sequential equity with compounding, applied at each trade's exit time.

    Sizing uses the equity available when the trade was opened, so positions that
    overlap across pairs do not each claim the same capital twice.
    """
    events: list[tuple[pd.Timestamp, int, int]] = []
    for position, trade in enumerate(trades.itertuples(index=False)):
        events.append((trade.decision_time, 0, position))
        events.append((trade.exit_time, 1, position))
    events.sort(key=lambda event: (event[0], event[1]))

    equity = initial_equity
    entry_equity = np.zeros(len(trades))
    equity_after = np.zeros(len(trades))
    net = trades["net_fraction"].to_numpy(dtype=float)
    curve_times: list[pd.Timestamp] = []
    curve_values: list[float] = []

    for timestamp, kind, position in events:
        if kind == 0:
            entry_equity[position] = equity
        else:
            equity += entry_equity[position] * net[position]
            equity_after[position] = equity
            curve_times.append(timestamp)
            curve_values.append(equity)

    curve = pd.Series(curve_values, index=pd.DatetimeIndex(curve_times))
    return equity_after, curve


def _metrics(
    trades: pd.DataFrame, curve: pd.Series, initial_equity: float, costs: CostModel
) -> Metrics:
    net_r = trades["net_r"].to_numpy(dtype=float)
    wins = net_r[net_r > 0]
    losses = net_r[net_r <= 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())

    final_equity = float(curve.iloc[-1]) if len(curve) else initial_equity
    total_return = final_equity / initial_equity - 1.0
    span_days = max(1.0, (curve.index[-1] - curve.index[0]).total_seconds() / 86400.0)
    years = span_days / 365.0
    if final_equity > 0:
        annualized = (final_equity / initial_equity) ** (1.0 / years) - 1.0
    else:
        annualized = -1.0

    daily = curve.resample("1D").last().ffill()
    daily_returns = daily.pct_change().dropna()
    sharpe = _annualized_ratio(daily_returns, daily_returns.std(ddof=0))
    downside = daily_returns[daily_returns < 0]
    sortino = _annualized_ratio(daily_returns, downside.std(ddof=0) if len(downside) else np.nan)

    running_max = curve.cummax()
    max_drawdown = float((1.0 - curve / running_max).max()) if len(curve) else 0.0

    total_hours = float(trades["hours_held"].sum())
    span_hours = span_days * 24.0
    pairs = max(1, trades["pair"].nunique())
    exposure = total_hours / (span_hours * pairs)

    return Metrics(
        trades=int(len(trades)),
        win_rate=float((net_r > 0).mean()),
        avg_win_r=float(wins.mean()) if len(wins) else 0.0,
        avg_loss_r=float(losses.mean()) if len(losses) else 0.0,
        profit_factor=float(gross_profit / gross_loss) if gross_loss > 0 else math.inf,
        expectancy_r=float(net_r.mean()),
        total_return=total_return,
        annualized_return=annualized,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        sortino=sortino,
        exposure=exposure,
        cost_drag_return=float(trades["cost_fraction"].sum()) if costs.round_trip > 0 else 0.0,
    )


def _annualized_ratio(returns: pd.Series, deviation: float) -> float:
    if len(returns) < 2 or not np.isfinite(deviation) or deviation == 0:
        return 0.0
    return float(returns.mean() / deviation * math.sqrt(365.0))


def _empty_metrics() -> Metrics:
    return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def buy_and_hold(
    bars_by_pair: dict[str, pd.DataFrame], initial_equity: float = 10_000.0
) -> Metrics:
    """Equal-weight, unlevered, no rebalancing after the first bar."""
    frames = []
    for pair, bars in bars_by_pair.items():
        series = bars["close"].copy()
        frames.append((series / series.iloc[0]).rename(pair))
    combined = pd.concat(frames, axis=1).ffill().dropna()
    curve = combined.mean(axis=1) * initial_equity

    daily = curve.resample("1D").last().ffill()
    daily_returns = daily.pct_change().dropna()
    downside = daily_returns[daily_returns < 0]
    span_days = max(1.0, (curve.index[-1] - curve.index[0]).total_seconds() / 86400.0)
    final_equity = float(curve.iloc[-1])
    return Metrics(
        trades=len(bars_by_pair),
        win_rate=0.0,
        avg_win_r=0.0,
        avg_loss_r=0.0,
        profit_factor=math.inf,
        expectancy_r=0.0,
        total_return=final_equity / initial_equity - 1.0,
        annualized_return=(final_equity / initial_equity) ** (365.0 / span_days) - 1.0,
        max_drawdown=float((1.0 - curve / curve.cummax()).max()),
        sharpe=_annualized_ratio(daily_returns, daily_returns.std(ddof=0)),
        sortino=_annualized_ratio(daily_returns, downside.std(ddof=0) if len(downside) else np.nan),
        exposure=1.0,
        cost_drag_return=0.0,
    )
