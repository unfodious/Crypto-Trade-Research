# CT-178 Binance Futures Metrics Import

Status: complete; historical external crowding dataset imported and initial screen run; no live
approval.

CT-177 found Binance Data Vision USD-M `daily/metrics` as the first feasible free/public archive
for CT-113 external futures positioning context. CT-178 implements a reproducible importer and runs
it for the historical windows needed to test CT-145/CT-156 beyond OHLCV-derived filters.

## Implementation

Added `crypto_trade_research.data.binance_futures_metrics` and the CLI entrypoint
`crypto-trade-ingest-binance-futures-metrics`.

The importer:

- downloads Binance Data Vision ZIP files from
  `data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{date}.zip`;
- parses 5-minute USD-M futures metrics as UTC point-in-time rows;
- writes raw and clean parquet files plus a manifest under ignored `data/generated/`;
- validates duplicate keys, nonnegative open interest, source availability timestamps, and
  per-symbol interval gaps;
- preserves blank ratio source values as nullable fields instead of converting them to zero.

Nullable ratio values are intentional. Treating blank top-trader/global/taker ratios as `0` would
create a false market signal. The next feature step must impute or mask these values explicitly.

## Import Command

```sh
.venv/bin/python -m crypto_trade_research.data.binance_futures_metrics \
  --symbols SOLUSDT,SUIUSDT,AVAXUSDT,ADAUSDT,ICPUSDT,ATOMUSDT,XRPUSDT,TONUSDT,DOTUSDT,BTCUSDT,ETHUSDT \
  --start-date 2024-07-01 \
  --end-date 2025-11-25 \
  --output-dir data/generated \
  --dataset-name ct178_data_vision_futures_metrics_dataset \
  --generator-version ct178.data-vision-futures-metrics.v1 \
  --generated-at 2026-05-27T21:30:00Z \
  --max-workers 16
```

Output manifest:

- `data/generated/ct178_data_vision_futures_metrics_dataset/manifest.json`

## Coverage

| Field | Value |
| --- | --- |
| Rows | `1,621,961` |
| Source ZIP files | `5,632` |
| Missing ZIP files | `0` |
| Symbols | `ADAUSDT`, `ATOMUSDT`, `AVAXUSDT`, `BTCUSDT`, `DOTUSDT`, `ETHUSDT`, `ICPUSDT`, `SOLUSDT`, `SUIUSDT`, `TONUSDT`, `XRPUSDT` |
| Min metrics time | `2024-07-01T00:05:00Z` |
| Max metrics time | `2025-11-25T00:00:00Z` |
| Rows per symbol | `147,451` |

This covers the three historical CT-113 holdout windows:

- H2 2024: `2024-07-01` through `2025-01-01`;
- H1 2025: `2025-01-01` through `2025-07-01`;
- Jul-Nov 2025: `2025-07-01` through `2025-11-25`.

## Source Quality Notes

The archive has no missing ZIP files for the CT-113 universe, but it is not perfectly regular:

- every symbol has interval gaps around `2024-10-28T16:40:00Z`,
  `2025-04-15T08:15:00Z`, `2025-07-21T16:31:26Z`, and
  `2025-08-29T06:40:00Z`;
- nullable ratio counts in the full dataset:
  - `count_toptrader_long_short_ratio`: `677`;
  - `sum_toptrader_long_short_ratio`: `281`;
  - `count_long_short_ratio`: `303`;
  - `sum_taker_long_short_vol_ratio`: `0`.

These gaps are small relative to the dataset size, but they must be handled point-in-time in feature
generation with bounded forward-fill and missingness flags.

## Selected-Trade Feature Screen

Added `crypto_trade_research.futures_metrics_selected_features` and the CLI entrypoint
`crypto-trade-build-futures-metrics-selected-features`.

The builder joins futures metrics to cached historical selected-trade rows using:

- same `symbol`;
- latest `metrics_time <= decision_time`;
- maximum metrics age `10` minutes;
- no future metrics bucket.

Generated feature parquets:

| Window | Rows | Metrics matched |
| --- | ---: | ---: |
| `2024H2` | `3,573` | `3,573` |
| `2025H1` | `5,682` | `5,682` |
| `2025JulNov` | `2,820` | `2,820` |

Config:

- `configs/ct178-futures-metrics-selected-features.json`;
- `configs/ct178-futures-metrics-abstention-matrix.json`.

Generated report:

- `data/generated/ct178_futures_metrics_abstention_matrix/report.json`;
- `data/generated/ct178_futures_metrics_abstention_matrix/report.md`.

## Initial Screen Results

The screen is selected-trade-only. It recomputes the cached trade outcomes after skipping selected
rows that match each predeclared futures-crowding rule. It does not rescore models and does not
replace full replay.

Most rules were unstable across windows, but one CT-145-family rule is worth full replay:

| Candidate | Rule | Window | Trades | Avg R | Max DD | PF |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `ct144_no_ton` | base | `2024H2` | `1,511` | `0.1455` | `3.74%` | `1.3029` |
| `ct144_no_ton` | base | `2025H1` | `2,242` | `-0.0083` | `9.85%` | `0.9849` |
| `ct144_no_ton` | base | `2025JulNov` | `1,255` | `0.0287` | `4.34%` | `1.0558` |
| `ct144_no_ton` | `oi_1h_expansion_high` | `2024H2` | `951` | `0.0633` | `1.92%` | `1.1356` |
| `ct144_no_ton` | `oi_1h_expansion_high` | `2025H1` | `1,703` | `0.0131` | `3.83%` | `1.0272` |
| `ct144_no_ton` | `oi_1h_expansion_high` | `2025JulNov` | `876` | `0.0172` | `3.11%` | `1.0361` |

`oi_1h_expansion_high` means: abstain when symbol futures open-interest notional expanded more than
`1.5%` over the prior hour. It reduces upside in strong windows, but it turns the previously
negative H1 2025 selected-trade screen positive and lowers drawdown materially in every window.

Other examples were not stable enough:

| Candidate | Rule | Weakness |
| --- | --- | --- |
| `ct144_no_ton` | `global_long_crowded` | good H1 but zero trades in Jul-Nov 2025 |
| `ct155_high_beta_plus_dot` | `oi_1h_expansion_high` | good H1 but negative H2 2024 |
| `ct155_high_beta_plus_dot` | `oi_1h_expansion_and_global_crowded` | good H1/Jul-Nov but negative H2 2024 |

## Decision

CT-178 succeeds as an import plus initial selected-trade screen.

No working model claim.

No paper-to-live promotion.

Keep CT-113 open.

## Next Step

Create the next CT-113 issue to run full historical replay for the CT-145-family OI-expansion
abstention candidate:

- add `fm_oi_value_change_1h > 0.015` as a point-in-time abstention filter;
- replay CT-145/`ct144_no_ton` over H2 2024, H1 2025, and Jul-Nov 2025 with full runner controls;
- compare against base, CT-176 OHLCV abstention, and no-trade;
- require positive average R after costs, `>=100` trades per OOS window, drawdown within gate,
  no-leakage join evidence, and stability across windows before any paper-trading promotion.
