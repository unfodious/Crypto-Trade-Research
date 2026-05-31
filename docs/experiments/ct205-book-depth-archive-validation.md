# CT-205 Binance book-depth archive validation

Issue: `CT-205`
Epic: `CT-113`

Status: complete; data source feasible; full matrix deferred to next issue; no working model claim.

## Question

CT-204 found that Binance Data Vision `data/futures/um/daily/bookDepth/{symbol}/` may be the only
free/public historical microstructure source worth trying before paying for vendor liquidation or
order-book archives.

CT-205 validates the data source before any new strategy matrix:

- archive coverage for old CT-113 windows;
- one reproducible import path;
- point-in-time depth features;
- smoke join to existing decision timestamps;
- small diagnostic check against a known rejected selected-trade family.

## Implementation

Added:

- `crypto_trade_research.data.binance_book_depth`;
- CLI: `crypto-trade-ingest-binance-book-depth`;
- `crypto_trade_research.book_depth_selected_features`;
- CLI: `crypto-trade-build-book-depth-selected-features`;
- smoke config: `configs/ct205-book-depth-selected-features-smoke.json`.

The book-depth importer writes:

- raw normalized rows: `raw/book_depth.parquet`;
- clean normalized rows: `clean/book_depth.parquet`;
- aggregated point-in-time feature rows: `features/book_depth_features.parquet`;
- manifest with hashes and source metadata.

Normalized source columns:

```text
timestamp,percentage,depth,notional
```

Normalized research row fields include:

- `symbol`;
- `depth_time`;
- `source_available_at`;
- `percentage`;
- `side`;
- `distance_pct`;
- `depth`;
- `notional`;
- source file, URL, and SHA256.

Feature rows aggregate each timestamp into:

- `bd_bid_notional_1pct`, `bd_bid_notional_2pct`, `bd_bid_notional_5pct`;
- `bd_ask_notional_1pct`, `bd_ask_notional_2pct`, `bd_ask_notional_5pct`;
- `bd_imbalance_1pct`, `bd_imbalance_2pct`, `bd_imbalance_5pct`;
- `bd_total_notional_1pct`, `bd_total_notional_2pct`, `bd_total_notional_5pct`;
- `bd_band_count`.

Point-in-time rule:

- use only book-depth rows with `depth_time <= decision_time`;
- join with bounded max age, initially `5` minutes;
- no daily aggregate that includes future rows is used.

## Coverage

Command:

```sh
python -m crypto_trade_research.data.binance_book_depth coverage \
  --symbols SOLUSDT,SUIUSDT,AVAXUSDT,ADAUSDT,ICPUSDT,ATOMUSDT,XRPUSDT,TONUSDT,DOTUSDT,BTCUSDT,ETHUSDT \
  --windows 2024h2:2024-07-01:2025-01-01,2025h1:2025-01-01:2025-07-01,2025julnov:2025-07-01:2025-11-25 \
  --output-json-path data/generated/ct205_book_depth_coverage/coverage.json \
  --output-markdown-path data/generated/ct205_book_depth_coverage/coverage.md \
  --max-workers 24
```

Result:

| Metric | Value |
| --- | ---: |
| Expected files | `5,632` |
| Available files | `5,632` |
| Missing files | `0` |
| Coverage | `100.00%` |
| Estimated compressed size | `2.20 GiB` |

Window coverage:

| Window | Files | Coverage |
| --- | ---: | ---: |
| H2 2024 | `2,024 / 2,024` | `100.00%` |
| H1 2025 | `1,991 / 1,991` | `100.00%` |
| Jul-Nov 2025 | `1,617 / 1,617` | `100.00%` |

Interpretation: the archive is complete enough for the old CT-113 holdout windows across the 11
USD-M symbols.

## Import Smoke

Sample command:

```sh
python -m crypto_trade_research.data.binance_book_depth ingest \
  --symbols SOLUSDT,SUIUSDT,AVAXUSDT,ADAUSDT,ICPUSDT,ATOMUSDT,XRPUSDT,TONUSDT,DOTUSDT,BTCUSDT,ETHUSDT \
  --start-date 2025-02-03 \
  --end-date 2025-02-04 \
  --output-dir data/generated \
  --dataset-name ct205_book_depth_join_sample \
  --generator-version ct205.join-smoke.v1 \
  --generated-at 2026-05-31T16:45:00Z \
  --max-workers 8
```

Result:

| Metric | Value |
| --- | ---: |
| Source files | `11` |
| Missing files | `0` |
| Raw rows | `316,800` |
| Feature rows | `31,680` |
| Min depth time | `2025-02-03T00:00:07Z` |
| Max depth time | `2025-02-03T23:59:31Z` |
| Warnings | `0` |

This matches the expected shape: `2,880` timestamps per symbol per day and 10 depth bands per
timestamp.

## Join Smoke

Command:

```sh
python -m crypto_trade_research.book_depth_selected_features \
  --config configs/ct205-book-depth-selected-features-smoke.json \
  --summary-path data/generated/ct205_book_depth_selected_features/summary.json
```

Joined sample:

- selected trades:
  `data/generated/ct172_pre_july_2025_holdout_replay/ct145_no_ton_negative_funding_paper_pack/selected_trades.parquet`;
- book-depth features:
  `data/generated/ct205_book_depth_join_sample/features/book_depth_features.parquet`;
- max depth age: `5` minutes.

Result:

| Metric | Value |
| --- | ---: |
| Selected rows scanned | `5,331` |
| Book-depth matched rows | `626` |
| Max matched age | `0.50` minutes |
| Average matched age | `0.27` minutes |

Only one day of book-depth data was imported for the smoke, so most CT-172 H1 selected rows were
expected to remain unmatched. The matched rows prove the point-in-time join path works for real
selected-trade timestamps.

## One-Day Diagnostic

This is a smoke diagnostic, not a strategy decision. It checks whether the imported 2025-02-03
sample trivially explains CT-172 selected-trade outcomes.

| Slice | Rows | Avg R | Positive rate |
| --- | ---: | ---: | ---: |
| All matched rows | `626` | `-0.2693` | `31.47%` |
| `bd_imbalance_1pct > 0` | `419` | `-0.2633` | `31.74%` |
| `bd_imbalance_1pct <= 0` | `207` | `-0.2815` | `30.92%` |
| High 1% total depth half | `313` | `-0.3659` | `29.07%` |
| Low 1% total depth half | `313` | `-0.1728` | `33.87%` |

Interpretation:

- one day does not show an obvious immediate edge;
- simple positive bid imbalance is not enough by itself;
- lower near-market total depth looked less bad than higher total depth in this one-day sample, but
  this is not enough evidence for a rule;
- full-window feature import is justified before deciding whether depth helps.

## Decision

`bookDepth` passes CT-205 as a data source:

- old-window archive coverage is complete for the 11-symbol CT-113 universe;
- sample import is reproducible and clean;
- feature aggregation is point-in-time;
- selected-trade join works with low age;
- the data size is manageable enough for a full feature cache.

Do not promote any strategy or paper plan from CT-205. The one-day diagnostic is negative on average
and only proves the mechanics.

Created `CT-206` for a full book-depth feature cache and controlled historical diagnostics.

## Safety

No live trading, paper runtime, order placement, leverage, margin, stop-loss, take-profit, exchange
API, or account state behavior was changed.

Backtests and diagnostics remain research evidence only.

CT-113 stays open.
