# CT-188 Timeframe Continuation Scan

Status: rejected as a filter-only higher-timeframe path; research-only evidence.

CT-188 tested whether higher-timeframe confirmation can turn the current CT-180/CT-184 1m entry
stream into a stronger monthly-return candidate.

## Thesis

From the strategy, regime, indicator, price-action, and risk skills, the plausible edge would be:

- trade only when the higher timeframe is already trending;
- avoid lower-timeframe chop and weak beta regimes;
- select entries with enough continuation energy for more `3R+` runners;
- improve average R without simply increasing account risk.

This scan tests that idea as a confirmation layer over the current core-3 trade stream.

## Method

Input replay reports:

- `data/generated/ct180_2024h2_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025h1_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025julnov_oi_high_or_europe_replay/replay_report.json`

Config and generated report:

- `configs/ct188-timeframe-continuation-scan.json`
- `data/generated/ct188_timeframe_continuation_scan/report.json`
- `data/generated/ct188_timeframe_continuation_scan/report.md`

The report:

1. rebuilds accepted CT-180 replay trades using frozen pack risk controls;
2. applies the core-3 `ADAUSDT`, `AVAXUSDT`, `SUIUSDT` daily cap of `10`;
3. joins point-in-time cached 5m/15m features;
4. evaluates predeclared higher-timeframe filters.

## Results

| Scenario | Trades | Avg R | Win rate | Profit factor | Stop touch | Clean `>=3R` runners |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `core3_base` | `916` | `0.1573` | `50.76%` | `1.377` | `29.69%` | `10.37%` |
| `core3_15m_trend_slope` | `613` | `0.1460` | `51.55%` | `1.363` | `27.08%` | `9.30%` |
| `core3_15m_trend_slope_riskon` | `562` | `0.1529` | `51.78%` | `1.381` | `26.51%` | `9.96%` |
| `core3_btc_eth_15m_up` | `587` | `0.1213` | `50.43%` | `1.289` | `28.28%` | `9.54%` |
| `core3_5m_15m_local_trend` | `619` | `0.1584` | `52.18%` | `1.396` | `27.46%` | `9.69%` |
| `core3_pullback_in_15m_trend` | `146` | `0.1248` | `47.95%` | `1.277` | `32.88%` | `13.01%` |
| `core3_breakout_in_15m_trend` | `382` | `0.1280` | `50.79%` | `1.334` | `23.82%` | `7.07%` |
| `core3_adx_15m_trend` | `423` | `0.1334` | `51.54%` | `1.332` | `26.95%` | `8.51%` |
| `core3_vol_exp_15m_trend` | `309` | `0.1103` | `51.13%` | `1.273` | `25.24%` | `6.47%` |

## Interpretation

The filter-only higher-timeframe path does not solve the monthly-return problem.

The best average-R row, `core3_5m_15m_local_trend`, is only `0.1584R` versus the `0.1573R` baseline.
That is not a meaningful improvement. Most higher-timeframe filters reduce runner share, and the
pullback variant has a slightly higher clean-runner share but only `146` trades, worse average R, and
higher stop-touch rate.

The result is consistent with CT-186 and CT-187: the current 1m entry stream has a modest positive
edge, but not enough large-runner structure for a `30%` monthly objective at sane risk.

## Decision

Reject CT-188 as a filter-only higher-timeframe continuation path.

Do not change CT-184 paper sizing, exits, or filters from this evidence.

The next hypothesis should build a true 5m/15m entry and label family, not merely add
higher-timeframe filters to the existing 1m entries.
