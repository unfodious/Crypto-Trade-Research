# CT-144 Per-Symbol Candidate Diagnostics

Date: 2026-05-27

Issue: CT-144

Epic: CT-113

## Decision

CT-144 tested the CT-141 negative-funding candidate per symbol and then tested compact symbol
combos derived from those diagnostics. The best practical result is not a single-symbol model. It is
a smaller basket that removes `TONUSDT` from CT-142:

- candidate: `ct144_no_ton`
- candidate symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`
- OOS trades: `275`
- average R after costs: `0.3959`
- rule-only average R: `-0.4591`
- max drawdown: `1.60%`
- profit factor: `1.7073`
- selected probability threshold: `0.55`
- selected expected-R threshold: `-0.20`
- external stability artifact status: `pass`

This improves the CT-142 no-DOT paper candidate (`0.3306` avg R, `269` trades, `2.32%` DD) while
keeping trade count high. It remains backtest evidence only. It should be prepared as a separate
paper-pack candidate before any forward-paper success claim.

## Thesis

The CT-141 no-DOT basket passed gates, but its symbol slices were uneven. CT-144 tested whether the
edge was broad enough to justify a basket, whether any single symbol was strong enough alone, and
whether removing weak slices could improve the paper candidate.

## Data

Same six-month data as CT-141:

- candle dataset: `ct121_six_month_core_futures_dataset`
- funding dataset: `ct128_six_month_funding_rate_dataset`
- train end: `2026-03-25T00:00:00Z`
- validation end: `2026-04-25T00:00:00Z`
- test end: `2026-05-25T00:00:00Z`

The full CT-130/CT-138 universe remains available for BTC/ETH context and breadth features. Only
candidate entries were restricted.

## Implementation

Added configs:

- `configs/ct144-per-symbol-candidate-diagnostics-matrix.json`
- `configs/ct144-core-symbol-combo-diagnostics-matrix.json`
- `configs/ct144-core-symbol-detailed-stability-matrix.json`

Generated artifacts:

- `data/generated/ct144_per_symbol_candidate_diagnostics/leaderboard.json`
- `data/generated/ct144_core_symbol_combo_diagnostics/leaderboard.json`
- `data/generated/ct144_core_symbol_detailed_stability/leaderboard.json`
- `data/generated/ct144_no_ton_detailed/stability_report.json`

Generated artifacts are not committed.

## Per-Symbol Results

| Symbol | Avg R | Rule Avg R | Trades | Max DD | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| SOLUSDT | `0.2845` | `-0.4923` | `37` | `0.75%` | positive but sparse |
| SUIUSDT | `-0.0193` | `-0.5475` | `122` | `10.13%` | reject |
| AVAXUSDT | `0.5393` | `-0.4054` | `49` | `1.73%` | positive but sparse |
| ADAUSDT | `0.5343` | `-0.1734` | `86` | `3.45%` | positive but sparse |
| ICPUSDT | `-0.0361` | `-0.5222` | `108` | `5.88%` | reject |
| TONUSDT | `-1.1750` | `-0.6177` | `7` | `0.45%` | reject |
| DOTUSDT | `0.1886` | `-0.5709` | `22` | `0.40%` | positive but sparse |

Single-symbol models did not produce a standalone paper candidate. The symbols with enough trades
were negative or too close to flat. The positive symbols were too sparse alone.

## Combo Results

| Experiment | Symbols | Avg R | Rule Avg R | Trades | Max DD | Profit Factor | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| core SOL/AVAX/ADA | SOL, AVAX, ADA | `0.4355` | `-0.3557` | `190` | `1.58%` | `1.8003` | supports |
| core + DOT | SOL, AVAX, ADA, DOT | `0.7341` | `-0.4451` | `11` | `0.94%` | `2.7181` | sparse reject |
| no TON | SOL, SUI, AVAX, ADA, ICP | `0.3959` | `-0.4591` | `275` | `1.60%` | `1.7073` | best practical |
| no TON + DOT | SOL, SUI, AVAX, ADA, ICP, DOT | `0.4665` | `-0.4843` | `106` | `1.47%` | `1.8768` | supports but narrower |

The top-N curve for `ct144_no_ton` stayed positive:

| Strategy | Trades | Avg R | Max DD | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| expected-R top1 | `234` | `0.3250` | `1.60%` | `1.5532` |
| expected-R top2 | `262` | `0.3708` | `1.62%` | `1.6510` |
| expected-R top3 | `275` | `0.3959` | `1.60%` | `1.7073` |
| expected-R top5 | `277` | `0.3846` | `1.76%` | `1.6817` |

## Stability Artifact

`ct144_no_ton` passed all explicit stability gates:

| Gate | Result |
| --- | --- |
| positive OOS expectancy | pass |
| beats rule-only OOS | pass |
| minimum trade count | pass (`275 >= 100`) |
| drawdown within limit | pass (`1.60% <= 8.00%`) |
| symbol breadth | pass (`100.00%` positive symbols) |
| session breadth | pass (`100.00%` positive sessions) |
| lucky-day concentration | pass (`38.66% <= 75.00%`) |
| nearby sensitivity | pass (`100.00%` positive variants) |

Symbol slices:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| SOLUSDT | `31` | `0.6637` |
| AVAXUSDT | `33` | `0.6432` |
| ADAUSDT | `53` | `0.6363` |
| SUIUSDT | `39` | `0.4404` |
| ICPUSDT | `119` | `0.1359` |

Session slices:

| Session | Trades | Avg R |
| --- | ---: | ---: |
| Asia | `69` | `0.4772` |
| Europe | `60` | `0.0250` |
| US | `146` | `0.5099` |

## Interpretation

Per-symbol training alone is not better than basket ranking. The useful lesson is symbol selection:
`TONUSDT` is consistently weak for this setup, while `SOLUSDT`, `AVAXUSDT`, and `ADAUSDT` provide
the cleanest expectancy and `ICPUSDT` provides useful volume when it competes inside the basket.

Compared with CT-142 no-DOT:

- avg R improved: `0.3306 -> 0.3959`
- OOS trades improved: `269 -> 275`
- max DD improved: `2.32% -> 1.60%`
- symbol/session breadth improved to `100%`
- candidate scope is still broad enough for paper collection.

## Next Step

Created CT-145 as the follow-up paper-pack issue for `ct144_no_ton`. Do not silently replace CT-142
automation. Run it as a separate stream or explicitly supersede CT-142 after review. No live trading
approval exists from these backtests.
