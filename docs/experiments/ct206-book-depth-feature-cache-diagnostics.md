# CT-206 book-depth feature cache and diagnostics

Issue: `CT-206`
Epic: `CT-113`

Status: complete; full replay justified; no working model claim.

## Question

CT-205 proved that Binance Data Vision USD-M `daily/bookDepth` exists for the old CT-113 windows.
CT-206 answers the next question: can we build a full historical feature cache and does a first
controlled diagnostic justify a real strategy replay?

## Implementation

Added streaming feature-cache support to `crypto_trade_research.data.binance_book_depth`.

The earlier CT-205 sample importer writes raw, clean, and feature rows in memory. That is fine for a
one-day smoke, but not for `5,632` historical zip files. CT-206 adds:

```sh
python -m crypto_trade_research.data.binance_book_depth feature-cache ...
```

The feature-cache path:

- downloads one source zip at a time through a bounded worker pool;
- validates raw rows per source file;
- aggregates each timestamp into feature rows;
- writes only feature rows into parquet;
- does not retain the full raw book-depth history in memory;
- writes a manifest with source row count, feature row count, file count, missing count, hashes, and
  warnings.

Also updated `crypto_trade_research.book_depth_selected_features` so it can join against multiple
monthly feature parquet files.

## Cache Build

The full archive was built as monthly chunks rather than three large window files. This made the job
recoverable after Docker/network hangs and keeps each parquet file small enough for follow-up
diagnostics.

The first Docker long-run stalled on a large H2 2024 cache write. The successful run used the local
`.venv` Python 3.12 environment for the data job and kept Docker for QA.

Summary:

| Metric | Value |
| --- | ---: |
| Monthly chunks | `17` |
| Source files | `5,632` |
| Missing files | `0` |
| Source rows | `160,319,680` |
| Feature rows | `16,031,968` |
| Feature parquet size | `1.82 GiB` |
| Warnings | `0` |

Window source files:

| Window | Files | Feature rows |
| --- | ---: | ---: |
| H2 2024 | `2,024` | `5,826,220` |
| H1 2025 | `1,991` | `5,688,532` |
| Jul-Nov 2025 | `1,617` | `4,517,216` |

Artifacts:

- cache summary: `data/generated/ct206_book_depth_feature_cache_summary/summary.json`;
- monthly manifests: `data/generated/ct206_book_depth_features_*/manifest.json`;
- monthly feature parquet files:
  `data/generated/ct206_book_depth_features_*/features/book_depth_features.parquet`.

## Join Coverage

Selected-trade joins:

| Window | Input rows | Matched rows | Match rate |
| --- | ---: | ---: | ---: |
| H2 2024 selected trades | `3,460` | `3,460` | `100.00%` |
| H1 2025 selected trades | `5,331` | `5,321` | `99.81%` |
| Jul-Nov 2025 selected trades | `2,629` | `2,629` | `100.00%` |

Accepted-trade joins:

| Window | Input rows | Matched rows | Match rate |
| --- | ---: | ---: | ---: |
| H2 2024 accepted trades | `1,511` | `1,511` | `100.00%` |
| H1 2025 accepted trades | `2,242` | `2,239` | `99.87%` |
| Jul-Nov 2025 accepted trades | `1,255` | `1,255` | `100.00%` |

The few unmatched H1 rows are outside the strict `5` minute max-age guard or sit on source edge
timestamps. The join quality is strong enough for full replay.

## Selected-Trade Diagnostic

Selected trades are broader than actual accepted trades, so this is mainly a quality screen.

Combined selected rows:

| Slice | Rows | Avg R | Positive rate | PF |
| --- | ---: | ---: | ---: | ---: |
| All matched selected rows | `11,410` | `-0.1726` | `36.27%` | `0.7189` |
| `bd_imbalance_1pct <= -0.10` | `1,972` | `-0.1626` | `36.92%` | `0.7466` |
| `-0.10 < bd_imbalance_1pct < 0.10` | `6,380` | `-0.1738` | `36.13%` | `0.7084` |
| `bd_imbalance_1pct >= 0.10` | `3,058` | `-0.1766` | `36.13%` | `0.7214` |

Interpretation: simple depth imbalance does not rescue the broad selected-candidate pool.

## Accepted-Trade Diagnostic

Accepted trades are the relevant path for the frozen CT-145 style strategy family.

Window baseline after book-depth join:

| Window | Accepted rows | Avg R | PF |
| --- | ---: | ---: | ---: |
| H2 2024 | `1,511` | `0.1455` | `1.3029` |
| H1 2025 | `2,239` | `-0.0077` | `0.9859` |
| Jul-Nov 2025 | `1,255` | `0.0287` | `1.0558` |
| Combined | `5,005` | `0.0477` | `1.0918` |

Near-market 1 percent imbalance:

| Slice | Rows | Avg R | PF |
| --- | ---: | ---: | ---: |
| `bd_imbalance_1pct <= -0.10` | `961` | `0.0762` | `1.1427` |
| `-0.10 < bd_imbalance_1pct < 0.10` | `2,752` | `0.0695` | `1.1401` |
| `bd_imbalance_1pct >= 0.10` | `1,292` | `-0.0200` | `0.9642` |

By window, the `bd_imbalance_1pct >= 0.10` bid-heavy slice is the weak slice:

| Window | Non-bid-heavy rows | Non-bid-heavy Avg R | Bid-heavy rows | Bid-heavy Avg R |
| --- | ---: | ---: | ---: | ---: |
| H2 2024 | `1,193` | `0.1416` | `318` | `0.1602` |
| H1 2025 | `1,576` | `0.0190` | `663` | `-0.0711` |
| Jul-Nov 2025 | `944` | `0.0695` | `311` | `-0.0952` |

Interpretation:

- H1 2025 and Jul-Nov 2025 improve materially if bid-heavy near-market states are excluded;
- H2 2024 does not support the same exclusion, because bid-heavy trades were still positive there;
- this is a diagnostic on accepted rows, not a full path replay;
- skipped accepted trades change later exposure, ranking, and opportunity path, so a full replay is
  required before any promotion.

## Decision

`bookDepth` is not rejected at CT-206.

The source is complete, joinable, and potentially useful as an abstention/context feature. The first
actionable hypothesis is:

> For the CT-145 family, near-market bid-heavy visible depth may mark weaker long entries in the
> failure windows, possibly because visible bid liquidity is being leaned on or pulled into downside
> pressure rather than acting as support.

Created `CT-207` to run a full book-depth abstention replay matrix.

Do not prepare a paper-trading plan from CT-206. No working model is claimed.

## Safety

No live trading, paper runtime, order placement, leverage, margin, stop-loss, take-profit, exchange
API, or account state behavior was changed.

Backtests and diagnostics remain research evidence only.

CT-113 stays open.
