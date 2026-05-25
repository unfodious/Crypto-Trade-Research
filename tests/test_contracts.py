from datetime import UTC, datetime

import pytest

from crypto_trade_research.contracts import MarketBar, ResearchRunConfig


def test_market_bar_requires_positive_ohlcv_values() -> None:
    bar = MarketBar(
        venue="binance-futures",
        symbol="BTCUSDT",
        timeframe="1h",
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=1234.5,
        funding_rate=0.0001,
        open_interest=10_000.0,
    )

    assert bar.symbol == "BTCUSDT"
    assert bar.quote_asset == "USDT"


def test_market_bar_rejects_invalid_price_range() -> None:
    with pytest.raises(ValueError, match="high must be greater than or equal"):
        MarketBar(
            venue="binance-futures",
            symbol="ETHUSDT",
            timeframe="15m",
            opened_at=datetime(2026, 1, 1, tzinfo=UTC),
            open=100.0,
            high=90.0,
            low=95.0,
            close=97.0,
            volume=10.0,
        )


def test_research_run_config_is_research_only_by_default() -> None:
    config = ResearchRunConfig(
        run_name="baseline-smoke",
        dataset_version="sample-v0",
        target_horizon_bars=24,
    )

    assert config.mode == "research"
    assert config.live_trading_enabled is False
