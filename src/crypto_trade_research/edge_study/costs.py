"""Cost model shared by the labeller, the backtest and the benchmarks.

Numbers come from `docs/research/strategy-audit-2026-09-21.md` section 5 so that
this study and the Go replay engine price a round trip identically.
"""

from __future__ import annotations

from dataclasses import dataclass

TAKER_FEE_PER_SIDE = 0.00045
SLIPPAGE_PER_SIDE = 0.0002
FUNDING_RATE_PER_8H = 0.0001


@dataclass(frozen=True)
class CostModel:
    """Fractional costs expressed on notional."""

    taker_fee_per_side: float = TAKER_FEE_PER_SIDE
    slippage_per_side: float = SLIPPAGE_PER_SIDE
    funding_rate_per_8h: float = FUNDING_RATE_PER_8H

    @classmethod
    def zero(cls) -> CostModel:
        return cls(0.0, 0.0, 0.0)

    @property
    def round_trip(self) -> float:
        """Entry + exit fee and slippage as a fraction of notional."""
        return 2.0 * (self.taker_fee_per_side + self.slippage_per_side)

    def funding_cost(self, side: int, hours_held: float) -> float:
        """Funding paid as a fraction of notional.

        Flat model, same as the Go replay engine: longs pay, shorts receive.
        A short therefore gets a small credit, which is why the sign matters.
        """
        settlements = max(0.0, hours_held) / 8.0
        return side * self.funding_rate_per_8h * settlements
