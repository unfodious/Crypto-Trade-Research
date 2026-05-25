# Data Contract

The research dataset starts with normalized bars and grows toward reproducible feature and label tables.

## Market Bar Fields

- `venue`: exchange or venue source, for example `binance-futures`.
- `symbol`: market symbol, for example `BTCUSDT`.
- `timeframe`: candle timeframe, for example `1m`, `15m`, or `1h`.
- `opened_at`: timezone-aware candle open timestamp.
- `open`, `high`, `low`, `close`: positive price values.
- `volume`: non-negative base or venue-defined volume.
- `funding_rate`: optional perpetual funding rate known at the appropriate time.
- `open_interest`: optional non-negative derivatives open interest.
- `spread_bps`: optional non-negative spread assumption.
- `maker_fee_bps`, `taker_fee_bps`: optional non-negative fee assumptions.

## Dataset Requirements

- Version every durable dataset.
- Record venue, symbol universe, timezone, candle source, and missing-data policy.
- Keep raw credentials and private exports out of git.
- Prevent leakage: labels and future returns must not be visible to feature builders.
- Keep cost assumptions explicit: fees, spread, slippage, funding, and unavailable-trade rules.

## Planned Tables

- `market_bars`: OHLCV plus derivatives and venue metadata.
- `features`: point-in-time features keyed by dataset, symbol, timeframe, timestamp.
- `labels`: target-before-stop, R multiple, MFE/MAE, forward returns, and no-trade outcomes.
- `backtest_trades`: simulated fills and lifecycle events.
- `evaluation_reports`: immutable run summaries and promotion evidence.
