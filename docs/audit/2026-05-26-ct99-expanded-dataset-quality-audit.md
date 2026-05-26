# CT-99 Expanded Dataset Quality And Leakage Audit

Date: 2026-05-26

Dataset manifest: `data/generated/ct96_expanded_core_futures_dataset/manifest.json`
Export manifest: `data/generated/ct96_expanded_core_futures_export/market_candles.csv.manifest.json`

Generated audit artifact: `data/generated/ct99_quality_audit/audit.json`

## Scope

This audit covers the CT-96 expanded 1m USD-M futures market dataset before broad model
experiments. It checks source coverage, candle continuity, duplicate keys, OHLC/volume validity,
source availability, label contamination, and feature/label boundary behavior.

The detailed CSV, Parquet, manifests, and audit JSON remain under ignored `data/generated/` paths.
This committed report contains only aggregate evidence.

## Dataset Summary

- Dataset name: `ct96_expanded_core_futures_dataset`
- Schema: `research.dataset.v1`
- Market type: `um_futures`
- Timeframe: `1m`
- Symbols: `ADAUSDT`, `ATOMUSDT`, `AVAXUSDT`, `BTCUSDT`, `DOTUSDT`, `ETHUSDT`, `ICPUSDT`,
  `SOLUSDT`, `SUIUSDT`, `TONUSDT`, `XRPUSDT`
- Rows: `1,425,600`
- Per-symbol rows: `129,600`
- Per-symbol open-day coverage: `90` days
- First open time: `2026-02-24T00:00:00Z`
- First close time: `2026-02-24T00:01:00Z`
- Last open time: `2026-05-24T23:59:00Z`
- Last close time: `2026-05-25T00:00:00Z`

The `close_time` range includes `2026-05-25T00:00:00Z` because the contract uses exclusive
candle close boundaries. Day coverage is therefore audited by `open_time` day.

## Coverage Table

| Symbol | Timeframe | Rows | Open days | First open | Last open | Max step |
| --- | --- | ---: | ---: | --- | --- | ---: |
| ADAUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| ATOMUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| AVAXUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| BTCUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| DOTUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| ETHUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| ICPUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| SOLUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| SUIUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| TONUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |
| XRPUSDT | 1m | 129,600 | 90 | 2026-02-24T00:00:00Z | 2026-05-24T23:59:00Z | 60s |

## Quality Checks

| Check | Result |
| --- | ---: |
| Unexpected schema rows | 0 |
| Unexpected market type rows | 0 |
| Duplicate candle keys | 0 |
| Invalid OHLC rows | 0 |
| Invalid volume/trade-count rows | 0 |
| Invalid time-order rows | 0 |
| Missing/partial open-day findings | 0 |
| Non-60-second step findings | 0 |
| `source_available_at > decision_time` rows | 0 |
| `source_available_at < close_time` rows | 0 |
| `source_available_at != close_time` rows | 0 |
| Label/outcome columns present in market candles | 0 |

## Leakage Boundary

The raw and clean market datasets contain only market-candle fields from `MARKET_CANDLE_COLUMNS`.
No label/outcome fields such as `target_before_stop`, `realized_r_after_costs`, `forward_return`,
`net_r`, `exit_time`, or `no_trade_reason` are present.

During this audit, a cross-symbol boundary defect was found and fixed in the research feature and
label generators:

- Feature rolling windows now reset per `(venue, market_type, symbol, timeframe)`.
- Label future windows now reset per `(venue, market_type, symbol, timeframe)`.
- Higher-timeframe feature alignment now filters by `(venue, market_type, symbol)` before applying
  `source_available_at <= decision_time` and `close_time <= decision_time`.

Regression tests were added for cross-symbol feature and label windows.

## Cost Assumptions

The current CT-91 and CT-93 real experiment configs use the same cost assumptions:

- Label `cost_pct`: `0.0007`
- Fee: `4.0` bps
- Slippage: `2.0` bps
- Funding: `0.0` bps
- Tie breaker: `stop_first`

CT-96 follow-up configs should either preserve these assumptions or explicitly document any
cost-sensitivity variant. Promotion evidence must beat rule-only and no-trade after costs.

## Decision

Dataset quality is acceptable for CT-96 follow-up experiments after the feature/label boundary fix.
Experiments remain blocked if any future generated feature, label, or experiment config reintroduces:

- non-zero gap or duplicate findings,
- source availability after decision time,
- label/outcome fields inside feature rows,
- cross-symbol or cross-timeframe rolling/future windows,
- undocumented cost assumption changes.
