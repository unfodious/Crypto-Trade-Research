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

## Real Backend Export Smoke

Use YouTrack `CT-88` for the first real historical futures dataset smoke. The source database is the
Crypto Trade backend `historical_candles` table, populated by the backend Binance public-data
importer. Keep all CSV, Parquet, and manifest outputs under ignored `data/generated/` paths.

From `/Users/unfodious/Projects/crypto-trade/backend`, export a bounded real slice:

```sh
DATABASE_URL='<local backend postgres DSN>' \
go run ./cmd/historical-data-export \
  -market um_futures \
  -pairs BTCUSDT,ETHUSDT \
  -periods 1m \
  -start 2025-07-01 \
  -end 2025-07-02 \
  -output /Users/unfodious/Projects/crypto-trade-research/data/generated/ct88_real_export/market_candles.csv
```

Then ingest the exported CSV from `/Users/unfodious/Projects/crypto-trade-research`:

```sh
uv run crypto-trade-ingest-market-dataset \
  --source-csv data/generated/ct88_real_export/market_candles.csv \
  --output-dir data/generated \
  --dataset-name ct88_real_market_dataset \
  --generator-version ct88.smoke.v1 \
  --generated-at 2026-05-26T05:14:00Z
```

Before model training, inspect both manifests:

- `data/generated/ct88_real_export/market_candles.csv.manifest.json`
- `data/generated/ct88_real_market_dataset/manifest.json`

The exporter manifest must record source filters, row count, close-time range, and exported CSV
SHA-256. The ingestion manifest must report row count, min/max close time, raw/clean Parquet paths,
and validation warnings. Treat warnings about sorting as acceptable only when cleaned output sorted
the rows deterministically; duplicate candles, missing candle gaps, invalid OHLC, or stale
`source_available_at` should block training until explained.

## Extension Points

Funding, open-interest, mark/index price, and execution-assumption joins should be added as separate point-in-time datasets with their own `source_available_at` fields. Do not merge them into raw candle ingestion in a way that hides publication timing.
