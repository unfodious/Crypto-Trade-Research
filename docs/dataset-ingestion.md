# Dataset Ingestion

The initial ingestion pipeline converts fake or exported market-candle CSV rows into versioned Parquet datasets plus a deterministic manifest.

## Supported Input

The first source format is a CSV matching the `market_candles` schema in `docs/data-contract.md`. It does not require live exchange credentials.

Required behavior:

- Normalize `venue`, `market_type`, `symbol`, assets, and `timeframe`.
- Parse all timestamps as UTC RFC3339 values.
- Preserve source metadata fields such as `data_source`, `source_file`, and `checksum`.
- Reject future label or realized outcome fields in raw signal rows.
- Reject duplicate candle keys, missing candles, impossible OHLC, zero or negative prices, and abnormal wicks.
- Write raw normalized rows separately from cleaned sorted rows.

## Deterministic Sample

Run:

```sh
make sample-dataset
```

This uses `tests/fixtures/ingestion_source/market_candles.csv` and writes ignored files under `data/generated/sample_market_dataset/`.

The manifest records:

- schema version
- dataset name
- generator name and version
- source format and path
- generation timestamp
- row count
- min/max close time
- raw and cleaned Parquet paths
- validation warnings

Pass `--generated-at` when reproducibility matters. Without it, the manifest uses the current UTC time.

## Extension Points

Funding, open-interest, mark/index price, and execution-assumption joins should be added as separate point-in-time datasets with their own `source_available_at` fields. Do not merge them into raw candle ingestion in a way that hides publication timing.
