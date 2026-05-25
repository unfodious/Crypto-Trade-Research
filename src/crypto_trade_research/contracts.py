"""Core contracts shared across the research pipeline."""

from dataclasses import dataclass
from datetime import datetime

_QUOTE_ASSETS = ("USDT", "USDC", "BUSD", "BTC", "ETH", "USD")


@dataclass(frozen=True, slots=True)
class MarketBar:
    """A normalized market candle with optional crypto derivatives context."""

    venue: str
    symbol: str
    timeframe: str
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    funding_rate: float | None = None
    open_interest: float | None = None
    spread_bps: float | None = None
    taker_fee_bps: float | None = None
    maker_fee_bps: float | None = None

    def __post_init__(self) -> None:
        text_fields = {
            "venue": self.venue,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }
        for field_name, value in text_fields.items():
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        if self.opened_at.tzinfo is None:
            raise ValueError("opened_at must be timezone-aware")

        for field_name in ("open", "high", "low", "close"):
            value = getattr(self, field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")

        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.high < max(self.open, self.close):
            raise ValueError("high must cover open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must cover open and close")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")

        optional_non_negative = {
            "open_interest": self.open_interest,
            "spread_bps": self.spread_bps,
            "taker_fee_bps": self.taker_fee_bps,
            "maker_fee_bps": self.maker_fee_bps,
        }
        for field_name, value in optional_non_negative.items():
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative")

    @property
    def quote_asset(self) -> str:
        """Best-effort quote asset derived from common crypto symbols."""

        normalized = self.symbol.upper()
        for quote_asset in _QUOTE_ASSETS:
            if normalized.endswith(quote_asset):
                return quote_asset
        return "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ResearchRunConfig:
    """Reproducible run metadata with an explicit research-only default."""

    run_name: str
    dataset_version: str
    target_horizon_bars: int
    mode: str = "research"
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.run_name.strip():
            raise ValueError("run_name must not be empty")
        if not self.dataset_version.strip():
            raise ValueError("dataset_version must not be empty")
        if self.target_horizon_bars <= 0:
            raise ValueError("target_horizon_bars must be positive")
        if self.mode != "research":
            raise ValueError("mode must remain research until promotion gates exist")
        if self.live_trading_enabled:
            raise ValueError("live_trading_enabled must remain false in research runs")
