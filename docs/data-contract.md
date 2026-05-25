# Crypto Trade Research Data Contract

Schema version: `research.dataset.v1`
Status: canonical for research ingestion and test fixtures.
Runtime owner: `crypto-trade`.
Research owner: `crypto-trade-research`.

## Purpose

`crypto-trade-research` owns research datasets, feature engineering, labels, backtests, and model evaluation. `crypto-trade` owns live execution, exchange integrations, account state, risk gates, and eventual inference integration. This contract defines the stable boundary between them.

The first source of truth for raw candles is the `crypto-trade` backend table `historical_candles`. Legacy `historical_charts` rows can be imported for compatibility, but they are lower quality because they do not include open price, volume, trade count, market type, or source checksums.

No production database migration is required for this contract.

## Dataset Layout

Research datasets SHOULD be written as partitioned Parquet once ingestion exists:

```text
datasets/
  research_dataset_v1/
    market_candles/venue=binance/market_type=um_futures/symbol=BTCUSDT/timeframe=1m/*.parquet
    derivatives/venue=binance/market_type=um_futures/symbol=BTCUSDT/*.parquet
    execution_assumptions/venue=binance/market_type=um_futures/symbol=BTCUSDT/*.parquet
    market_metadata/venue=binance/symbol=BTCUSDT/*.parquet
    derived_features/schema_version=research.dataset.v1/*.parquet
    labels/schema_version=research.dataset.v1/*.parquet
    backtest_results/schema_version=research.dataset.v1/*.parquet
```

Committed sample data lives only under `tests/fixtures/research_dataset_v1/` and is fake.

## Common Rules

- Timezone: all timestamps are UTC and serialized as RFC3339 strings with `Z`.
- Candle boundary: `open_time` is inclusive, `close_time` is exclusive for joins. A candle is available to a strategy only at or after `close_time`.
- Decision time: `decision_time` is the timestamp at which a signal, feature row, label anchor, or backtest decision is evaluated.
- Join rule: a row may join another dataset only when `source_available_at <= decision_time`.
- Numeric storage: Parquet decimals are preferred for prices, quantities, fees, and rates. Float64 is acceptable for model matrices after a documented conversion step.
- Versioning: every generated dataset records `schema_version`, `generator_name`, `generator_version`, and `generated_at`.
- Symbol naming: use exchange symbols such as `BTCUSDT`. Do not invent separators in canonical fields.
- Venue naming: use lowercase exchange names such as `binance`.
- Market type: `spot`, `um_futures`, or `cm_futures`.

## Availability Classes

Every field falls into one of these classes:

- `signal_time`: available at the decision time without looking ahead.
- `post_close`: available only after the source candle/event close time.
- `after_the_fact`: label, realized outcome, or backtest result not usable for signal generation.
- `static_metadata`: exchange metadata valid for the row's timestamp.
- `assumption`: research assumption supplied by configuration, not observed market data.

Features may use only `signal_time`, `post_close` rows whose `source_available_at <= decision_time`, `static_metadata`, and `assumption` fields. Labels and backtest results are always `after_the_fact`.

## Raw Market Candles

Dataset: `market_candles`

Primary key:

- `schema_version`
- `venue`
- `market_type`
- `symbol`
- `timeframe`
- `open_time`
- `close_time`

| Field | Type | Availability | Required | Notes |
| --- | --- | --- | --- | --- |
| `schema_version` | string | static_metadata | yes | `research.dataset.v1` |
| `venue` | string | static_metadata | yes | Example: `binance` |
| `market_type` | enum | static_metadata | yes | `spot`, `um_futures`, `cm_futures` |
| `symbol` | string | static_metadata | yes | Exchange symbol, e.g. `BTCUSDT` |
| `base_asset` | string | static_metadata | yes | Example: `BTC` |
| `quote_asset` | string | static_metadata | yes | Example: `USDT` |
| `timeframe` | string | static_metadata | yes | `1m`, `3m`, `5m`, `15m`, `1h`, `4h`, `1d` |
| `open_time` | timestamp_utc | post_close | yes | Inclusive interval start |
| `close_time` | timestamp_utc | post_close | yes | Exclusive interval end and safe signal timestamp |
| `source_available_at` | timestamp_utc | signal_time | yes | Earliest time this row can be used |
| `open` | decimal | post_close | yes | Positive |
| `high` | decimal | post_close | yes | `high >= low`, contains open/close |
| `low` | decimal | post_close | yes | Positive |
| `close` | decimal | post_close | yes | Positive |
| `volume` | decimal | post_close | yes | Base asset volume |
| `quote_volume` | decimal | post_close | yes | Quote asset volume |
| `number_of_trades` | int64 | post_close | yes | Non-negative |
| `taker_buy_base_volume` | decimal | post_close | yes | Non-negative |
| `taker_buy_quote_volume` | decimal | post_close | yes | Non-negative |
| `data_source` | string | static_metadata | yes | Example: `postgres:historical_candles` |
| `source_file` | string/null | static_metadata | no | Import provenance |
| `checksum` | string/null | static_metadata | no | Import checksum |

For closed-candle strategies, `source_available_at` SHOULD equal `close_time`. If an exchange API publishes finalized candles with a known delay, use `close_time + delay`.

## Crypto Derivatives Data

Dataset: `derivatives`

Use sparse event rows keyed by `venue`, `market_type`, `symbol`, `event_time`, and `source_available_at`.

| Field | Type | Availability | Required | Notes |
| --- | --- | --- | --- | --- |
| `funding_rate` | decimal/null | signal_time or post_close | no | Use only after exchange publishes it |
| `next_funding_time` | timestamp_utc/null | signal_time | no | Scheduled future funding timestamp can be known ahead of settlement |
| `open_interest` | decimal/null | post_close | no | Avoid joining later snapshots into earlier decisions |
| `mark_price` | decimal/null | signal_time | no | Safe only at or before `decision_time` |
| `index_price` | decimal/null | signal_time | no | Safe only at or before `decision_time` |
| `basis` | decimal/null | derived | no | `mark_price - index_price` or configured alternative |

Current backend production schema does not have canonical derivatives history. Until added, research ingestion MUST leave these fields null or load them from explicitly versioned offline sources.

## Execution Assumptions

Dataset: `execution_assumptions`

These are assumptions, not market observations. They must be versioned because model results depend on them.

| Field | Type | Availability | Required | Notes |
| --- | --- | --- | --- | --- |
| `maker_fee_rate` | decimal | assumption | yes | Fee fraction, e.g. `0.0002` |
| `taker_fee_rate` | decimal | assumption | yes | Fee fraction, e.g. `0.0004` |
| `spread_bps` | decimal | assumption | yes | Conservative spread estimate |
| `slippage_bps` | decimal | assumption | yes | Conservative market-impact estimate |
| `slippage_model` | string | assumption | yes | Example: `fixed_bps_v1` |
| `min_notional` | decimal | static_metadata | yes | Exchange constraint for the timestamp |
| `quantity_precision` | int32 | static_metadata | yes | Exchange constraint for the timestamp |
| `price_precision` | int32 | static_metadata | yes | Exchange constraint for the timestamp |
| `effective_from` | timestamp_utc | static_metadata | yes | Inclusive |
| `effective_to` | timestamp_utc/null | static_metadata | no | Exclusive; null means still active |

## Market Metadata

Dataset: `market_metadata`

| Field | Type | Availability | Required | Notes |
| --- | --- | --- | --- | --- |
| `symbol_status` | string | static_metadata | yes | Example: `TRADING`, `BREAK`, `DELISTED` |
| `launch_time` | timestamp_utc/null | static_metadata | no | First tradable time if known |
| `delist_time` | timestamp_utc/null | static_metadata | no | Exclusive end of tradability |
| `contract_type` | string/null | static_metadata | no | Example: `PERPETUAL` |
| `base_asset` | string | static_metadata | yes | Example: `BTC` |
| `quote_asset` | string | static_metadata | yes | Example: `USDT` |
| `margin_asset` | string/null | static_metadata | no | Futures only |

Survivorship rule: datasets must include inactive/delisted symbols when the research period includes them. Filtering only currently active symbols creates survivorship bias.

## Derived Features

Dataset: `derived_features`

Derived feature rows are keyed by `schema_version`, `feature_set_version`, `venue`, `market_type`, `symbol`, `timeframe`, and `decision_time`.

Required fields:

- `feature_set_version`
- `decision_time`
- `source_window_start`
- `source_window_end`
- `source_available_at`
- `feature_values`

`feature_values` can be a wide Parquet schema or a struct/map, but the generated dataset must include a manifest listing feature names, units, lookback windows, and input datasets.

Allowed examples:

- Market-regime features.
- Technical indicators.
- Price-action structure.
- Volatility and range features.
- Participation/volume features.
- Multi-timeframe context.

Forbidden examples:

- Future return, future high/low, target hit, stop hit, or realized PnL.
- Funding settlement not yet published at `decision_time`.
- Any label or backtest outcome field.

## Labels

Dataset: `labels`

Labels are keyed by `label_set_version`, `venue`, `market_type`, `symbol`, `timeframe`, and `decision_time`.

Required labels for the first supervised baselines:

- `forward_return_1`
- `forward_return_3`
- `forward_return_12`
- `max_favorable_excursion_r`
- `max_adverse_excursion_r`
- `target_before_stop`
- `expected_r_after_costs`
- `no_trade_reason`

All label fields are `after_the_fact` and MUST NOT be available to feature generation.

## Backtest Results

Dataset: `backtest_results`

Backtest rows describe strategy decisions and outcomes under explicit execution assumptions.

Required fields:

- `backtest_id`
- `strategy_version`
- `feature_set_version`
- `label_set_version`
- `execution_assumption_version`
- `decision_time`
- `side`
- `entry_price`
- `stop_price`
- `target_price`
- `size`
- `gross_r`
- `fees_r`
- `slippage_r`
- `funding_r`
- `net_r`
- `exit_time`
- `exit_reason`

Backtest results are `after_the_fact` and are never valid inputs to model training except as evaluation targets in explicitly separated analysis.

## Optional Future Data

Optional future datasets may include:

- Liquidation estimates.
- Order-book snapshots.
- News or macro events.
- Exchange outage/event calendars.

Each future dataset must define `event_time`, `source_available_at`, and field-level availability before use.

## Leakage Risks And Controls

| Risk | Control |
| --- | --- |
| Joining future candles into current features | Join only where `close_time <= decision_time` and `source_available_at <= decision_time` |
| Using same candle close before the candle is closed | Treat `close_time` as the earliest safe timestamp for closed-candle features |
| Funding or open-interest snapshots published after decision time | Store `source_available_at`; never infer availability from event labels alone |
| Survivorship bias | Include launch/delist periods and inactive symbols in metadata |
| Cost leakage | Keep execution assumptions versioned and independent from realized strategy outcomes |
| Label contamination | Store labels in a separate dataset; feature builders cannot read label paths |
| Parameter mining | Record generator versions, feature set versions, walk-forward splits, and backtest IDs |

## Mapping From `crypto-trade`

Canonical source: `backend/database/migrations/20260525170000_create_historical_candles_table.up.sql`

| Backend table/field | Research field | Rule |
| --- | --- | --- |
| `historical_candles.pair` | `symbol` | Copy as exchange symbol |
| `historical_candles.period` | `timeframe` | Copy |
| `historical_candles.market_type` | `market_type` | Copy |
| `historical_candles.data_source` | `data_source` | Copy |
| `historical_candles.open_time` | `open_time` | Interpret as UTC |
| `historical_candles.close_time` | `close_time`, `source_available_at` | Interpret as UTC; default availability equals close time |
| `historical_candles.open` | `open` | Copy decimal |
| `historical_candles.high` | `high` | Copy decimal |
| `historical_candles.low` | `low` | Copy decimal |
| `historical_candles.close` | `close` | Copy decimal |
| `historical_candles.volume` | `volume` | Copy base volume |
| `historical_candles.quote_volume` | `quote_volume` | Copy quote volume |
| `historical_candles.number_of_trades` | `number_of_trades` | Copy |
| `historical_candles.taker_buy_base_volume` | `taker_buy_base_volume` | Copy |
| `historical_candles.taker_buy_quote_volume` | `taker_buy_quote_volume` | Copy |
| `historical_candles.source_file` | `source_file` | Copy nullable |
| `historical_candles.checksum` | `checksum` | Copy nullable |
| `pairs.symbol` | `symbol` metadata | Optional metadata enrichment |
| `pairs.is_active` | `symbol_status` | Map true to active/trading only when exchange metadata is unavailable |

Legacy source: `historical_charts`

| Legacy field | Research field | Rule |
| --- | --- | --- |
| `pair` | `symbol` | Copy |
| `period` | `timeframe` | Copy |
| `close_time` | `open_time`, `close_time`, `source_available_at` | Use as all three only for compatibility; mark `data_source=legacy:historical_charts` |
| `close` | `open`, `close` | Copy close into open only for compatibility; not valid for high-quality OHLC research |
| `high` | `high` | Copy |
| `low` | `low` | Copy |

Legacy rows SHOULD NOT be mixed with canonical rows unless downstream experiments explicitly track the lower quality data source.
