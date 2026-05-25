"""Typed schema for the Crypto Trade research data contract.

The classes intentionally use only the Python standard library so the contract
can be imported before the research dependency stack is scaffolded.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

SCHEMA_VERSION = "research.dataset.v1"


class Availability(StrEnum):
    SIGNAL_TIME = "signal_time"
    POST_CLOSE = "post_close"
    AFTER_THE_FACT = "after_the_fact"
    STATIC_METADATA = "static_metadata"
    ASSUMPTION = "assumption"
    DERIVED = "derived"


class MarketType(StrEnum):
    SPOT = "spot"
    UM_FUTURES = "um_futures"
    CM_FUTURES = "cm_futures"


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    parquet_type: str
    availability: Availability
    required: bool
    description: str


@dataclass(frozen=True)
class DatasetVersion:
    schema_version: str
    generator_name: str
    generator_version: str
    generated_at: datetime


@dataclass(frozen=True)
class MarketCandle:
    schema_version: str
    venue: str
    market_type: MarketType
    symbol: str
    base_asset: str
    quote_asset: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    source_available_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    number_of_trades: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal
    data_source: str
    source_file: str | None = None
    checksum: str | None = None


@dataclass(frozen=True)
class DerivativesSnapshot:
    schema_version: str
    venue: str
    market_type: MarketType
    symbol: str
    event_time: datetime
    source_available_at: datetime
    funding_rate: Decimal | None = None
    next_funding_time: datetime | None = None
    open_interest: Decimal | None = None
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    basis: Decimal | None = None


@dataclass(frozen=True)
class ExecutionAssumption:
    schema_version: str
    execution_assumption_version: str
    venue: str
    market_type: MarketType
    symbol: str
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal
    spread_bps: Decimal
    slippage_bps: Decimal
    slippage_model: str
    min_notional: Decimal
    quantity_precision: int
    price_precision: int
    effective_from: datetime
    effective_to: datetime | None = None


@dataclass(frozen=True)
class MarketMetadata:
    schema_version: str
    venue: str
    market_type: MarketType
    symbol: str
    base_asset: str
    quote_asset: str
    symbol_status: str
    launch_time: datetime | None = None
    delist_time: datetime | None = None
    contract_type: str | None = None
    margin_asset: str | None = None


@dataclass(frozen=True)
class DerivedFeatureRow:
    schema_version: str
    feature_set_version: str
    venue: str
    market_type: MarketType
    symbol: str
    timeframe: str
    decision_time: datetime
    source_window_start: datetime
    source_window_end: datetime
    source_available_at: datetime
    feature_values: Mapping[str, float]


@dataclass(frozen=True)
class LabelRow:
    schema_version: str
    label_set_version: str
    venue: str
    market_type: MarketType
    symbol: str
    timeframe: str
    decision_time: datetime
    forward_return_1: Decimal | None
    forward_return_3: Decimal | None
    forward_return_12: Decimal | None
    max_favorable_excursion_r: Decimal | None
    max_adverse_excursion_r: Decimal | None
    target_before_stop: bool | None
    expected_r_after_costs: Decimal | None
    no_trade_reason: str | None


@dataclass(frozen=True)
class BacktestResultRow:
    schema_version: str
    backtest_id: str
    strategy_version: str
    feature_set_version: str
    label_set_version: str
    execution_assumption_version: str
    venue: str
    market_type: MarketType
    symbol: str
    timeframe: str
    decision_time: datetime
    side: Side
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    size: Decimal
    gross_r: Decimal
    fees_r: Decimal
    slippage_r: Decimal
    funding_r: Decimal
    net_r: Decimal
    exit_time: datetime | None
    exit_reason: str | None


MARKET_CANDLE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "schema_version",
        "string",
        Availability.STATIC_METADATA,
        True,
        "Dataset schema version.",
    ),
    FieldSpec(
        "venue",
        "string",
        Availability.STATIC_METADATA,
        True,
        "Exchange name such as binance.",
    ),
    FieldSpec(
        "market_type",
        "string",
        Availability.STATIC_METADATA,
        True,
        "spot, um_futures, or cm_futures.",
    ),
    FieldSpec(
        "symbol",
        "string",
        Availability.STATIC_METADATA,
        True,
        "Exchange symbol such as BTCUSDT.",
    ),
    FieldSpec("timeframe", "string", Availability.STATIC_METADATA, True, "Candle period."),
    FieldSpec(
        "open_time",
        "timestamp[us, UTC]",
        Availability.POST_CLOSE,
        True,
        "Inclusive candle start.",
    ),
    FieldSpec(
        "close_time",
        "timestamp[us, UTC]",
        Availability.POST_CLOSE,
        True,
        "Exclusive candle end.",
    ),
    FieldSpec(
        "source_available_at",
        "timestamp[us, UTC]",
        Availability.SIGNAL_TIME,
        True,
        "Earliest safe join time.",
    ),
    FieldSpec("open", "decimal128", Availability.POST_CLOSE, True, "Open price."),
    FieldSpec("high", "decimal128", Availability.POST_CLOSE, True, "High price."),
    FieldSpec("low", "decimal128", Availability.POST_CLOSE, True, "Low price."),
    FieldSpec("close", "decimal128", Availability.POST_CLOSE, True, "Close price."),
    FieldSpec("volume", "decimal128", Availability.POST_CLOSE, True, "Base asset volume."),
    FieldSpec("quote_volume", "decimal128", Availability.POST_CLOSE, True, "Quote asset volume."),
    FieldSpec("number_of_trades", "int64", Availability.POST_CLOSE, True, "Exchange trade count."),
    FieldSpec(
        "taker_buy_base_volume",
        "decimal128",
        Availability.POST_CLOSE,
        True,
        "Taker buy base volume.",
    ),
    FieldSpec(
        "taker_buy_quote_volume",
        "decimal128",
        Availability.POST_CLOSE,
        True,
        "Taker buy quote volume.",
    ),
    FieldSpec("data_source", "string", Availability.STATIC_METADATA, True, "Source provenance."),
    FieldSpec(
        "source_file",
        "string",
        Availability.STATIC_METADATA,
        False,
        "Optional source file.",
    ),
    FieldSpec(
        "checksum",
        "string",
        Availability.STATIC_METADATA,
        False,
        "Optional source checksum.",
    ),
)
