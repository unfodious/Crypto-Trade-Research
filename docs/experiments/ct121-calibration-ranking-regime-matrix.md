# CT-121 Calibration Ranking And Regime Matrix

Date: 2026-05-26

Issue: `CT-121`
Epic: `CT-113`

## Decision

Rejected. CT-121 improved the strict h12 pocket through validation-selected probability
calibration and top-N ranking, but every positive row remained far below the `>=100` OOS trade
gate. No paper-trading candidate is approved.

CT-113 remains open.

Follow-up issue: `CT-122`, memory-safe six-month regime-conditioned ranking matrix.

## Data Expansion Check

Six-month data was technically feasible and was generated for the same CT-96 symbol universe:

- Dataset: `ct121_six_month_core_futures_dataset`
- Rows: `2,867,040`
- Symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`,
  `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`
- Window: `2025-11-25T00:00:00Z` to `2026-05-25T00:00:00Z`
- Manifest: `data/generated/ct121_six_month_core_futures_dataset/manifest.json`

The full-universe six-month CT-121 matrix could not complete in the current Docker runner. The
runner was killed with exit `137` during label generation after successfully building `2,867,040`
feature rows. This is a runner-memory blocker, not a data availability blocker.

The controlled CT-121 matrix therefore ran on the current CT-96 90-day dataset:

- Dataset: `data/generated/ct96_expanded_core_futures_dataset/manifest.json`
- Rows: `1,425,600`
- Split: train end `2026-04-25T00:00:00Z`, validation end `2026-05-10T00:00:00Z`, test end
  `2026-05-25T00:00:00Z`

## Setup

Starting point: strict h12 positive pocket from CT-119/CT-120.

Candidate setup:

- `volatility_expansion_20 >= 1.3`
- `close_location >= 0.7`
- `risk_on_score_20 >= 0.5`

Label:

- long
- 12-bar horizon
- 0.4% stop
- 0.8% target
- 0.07% cost
- `stop_first` tie breaker

Calibration and ranking:

- validation-only probability threshold sweep: `0.40` through `0.80`
- selected threshold: `0.60`
- explicit top-N ranking: top 1, 2, 3, and 5 per decision timestamp

## Results

| Experiment | Decision | Avg R | Rule Avg R | Trades | Max DD | Selected p | Failed gates |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `ct121_h12_strict_calibrated_unbounded` | reject | -0.0295 | -0.5582 | 55 | 6.07% | 0.60 | edge, walk-forward, minimum trade count, stability, paper plan |
| `ct121_h12_strict_calibrated_top1` | reject | 0.2694 | -0.5582 | 27 | 3.69% | 0.60 | minimum trade count, stability, paper plan |
| `ct121_h12_strict_calibrated_top2` | reject | 0.2179 | -0.5582 | 28 | 4.41% | 0.60 | minimum trade count, stability, paper plan |
| `ct121_h12_strict_calibrated_top3` | reject | 0.0472 | -0.5582 | 27 | 4.40% | 0.60 | minimum trade count, stability, paper plan |
| `ct121_h12_strict_calibrated_top5` | reject | 0.0472 | -0.5582 | 27 | 4.40% | 0.60 | minimum trade count, stability, paper plan |

Baseline comparison for the top1 run:

- no-trade OOS: `0` trades, `0.0000` average R
- rule-only OOS: `3,526` trades, `-0.5582` average R, `100.00%` max DD
- single-feature OOS: `1,395` trades, `-0.4761` average R, `99.40%` max DD
- multifeature unbounded OOS: `55` trades, `-0.0295` average R, `6.07%` max DD
- multifeature top1 OOS: `27` trades, `0.2694` average R, `3.69%` max DD

Validation threshold sweep selected `0.60`:

| Threshold | Validation trades | Validation Avg R | Validation Max DD |
| ---: | ---: | ---: | ---: |
| 0.40 | 398 | -0.4062 | 58.86% |
| 0.45 | 398 | -0.4062 | 58.86% |
| 0.50 | 392 | -0.4097 | 58.82% |
| 0.55 | 220 | -0.2477 | 26.80% |
| 0.60 | 22 | 0.3250 | 3.69% |
| 0.65 | 4 | -1.1750 | 3.14% |
| 0.70 | 1 | -1.1750 | 0.83% |
| 0.75 | 0 | 0.0000 | 0.00% |
| 0.80 | 0 | 0.0000 | 0.00% |

## Regime Diagnostics

The strict pocket is still too sparse, but diagnostics suggest where a follow-up should look after
the six-month runner is memory-safe:

- BTC/ETH trend regime: `both_above_ma` had `43` selected signals at `0.0808` average R; `mixed`
  had `12` at `-0.4250`.
- Volatility bucket: `normal` had `24` signals at `0.2000`; `disorderly` had `8` at `0.3250`;
  `expanded` had `23` at `-0.3924`.
- Market breadth: `risk_off` had only `5` signals but `0.6250` average R; `risk_on` had `37`
  signals at `-0.1209`.

These are diagnostics, not promotion evidence. Slice counts are too small and were observed after
the matrix, so CT-122 must predeclare any regime-conditioned variants before rerunning.

## Conclusion

Probability calibration and top-N ranking help isolate the positive strict pocket, especially top1
and top2, but they do not solve the OOS sample-count problem. The best CT-121 row has positive
expectancy and drawdown within gate, but only `27` trades against the `100` minimum.

Backtests are research evidence only. CT-121 does not produce a working model and does not approve
paper or live trading.
