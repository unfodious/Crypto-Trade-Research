# CT-138 Regime And Symbol Refinement Matrix

Date: 2026-05-27

Issue: CT-138

Epic: CT-113

## Decision

CT-138 found a refined negative-funding candidate that improves the CT-130 base in historical
six-month evidence. It is eligible for a separate paper-pack update issue, but it is not a working
model and not live-trading approved.

Best refinement:

- candidate: `ct138_no_weak_symbols_no_riskoff_top3`
- side: long
- horizon: `12` bars
- strategy: expected-R ridge top3 with existing risk controls
- OOS trades: `118`
- average R after costs: `0.4521`
- rule-only average R: `-0.5104`
- max drawdown: `1.91%`
- profit factor: `1.8408`
- selected expected-R threshold: `-0.10`
- stability artifact status: `pass`

This dominates the CT-130 base on expectancy and drawdown, but it has lower trade count and a more
constrained symbol/regime scope. The active CT-137 forward collector should not be silently replaced.
Created CT-139 to prepare a separate refined paper pack and decide whether to schedule it.

## Thesis

CT-130 behaved like a crowded-short / negative-funding long edge, not generic long alpha. Its
weakest historical slices were risk-off conditions and BTC/ETH/XRP/ATOM exposure. CT-138 tested
whether conservative exclusions could improve stability without merely mining a tiny pocket.

## Data

Same six-month data as CT-130:

- candle dataset: `ct121_six_month_core_futures_dataset`
- funding dataset: `ct128_six_month_funding_rate_dataset`
- all feature joins remain point-in-time;
- train end: `2026-03-25T00:00:00Z`
- validation end: `2026-04-25T00:00:00Z`
- test end: `2026-05-25T00:00:00Z`

## Implementation

Added `candidate_setup.symbols` support in the baseline runner. This keeps the full symbol universe
available for BTC/ETH context and breadth features, while restricting only candidate entries to a
predeclared symbol set.

Added configs:

- `configs/ct138-regime-symbol-refinement-matrix.json`
- `configs/ct138-no-weak-symbols-no-riskoff-base.json`

Generated artifacts:

- `data/generated/ct138_regime_symbol_refinement_matrix/leaderboard.json`
- `data/generated/ct138_regime_symbol_refinement_matrix/leaderboard.md`
- `data/generated/ct138_regime_symbol_refinement_matrix/stability_report.json`
- `data/generated/ct138_no_weak_symbols_no_riskoff_top3_detail/baseline_report.json`

Generated artifacts are not committed.

## Matrix Results

| Experiment | Avg R | Rule Avg R | Trades | Max DD | Selected E[R] | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| CT-130 base recheck | `0.2620` | `-0.6642` | `238` | `7.20%` | `-0.20` | baseline |
| no risk-off soft | `0.2956` | `-0.5141` | `204` | `1.67%` | `-0.20` | supports |
| mixed/risk-on | `0.3089` | `-0.4917` | `186` | `1.75%` | `-0.20` | supports |
| no weak symbols | `0.3511` | `-0.6383` | `230` | `7.08%` | `-0.20` | supports |
| core symbols only | `0.2390` | `-0.6445` | `157` | `7.48%` | `-0.20` | weaker |
| no weak symbols + no risk-off | `0.4521` | `-0.5104` | `118` | `1.91%` | `-0.10` | best |
| core symbols + no risk-off | `0.1107` | `-0.5669` | `63` | `2.56%` | `-0.10` | sparse reject |

The best variant is not the narrowest core-symbol slice. It keeps seven candidate symbols and uses
the risk-off exclusion to remove the worst regime.

## Best Candidate Rules

Universe remains the full CT-130 universe for context features, but candidate entries are restricted
to:

- `SOLUSDT`
- `SUIUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `ICPUSDT`
- `TONUSDT`
- `DOTUSDT`

Candidate filters:

- `funding_rate <= -0.00002`
- `funding_rate_zscore_20 <= -0.25`
- `close_location >= 0.45`
- `risk_on_score_20 >= 0.35`
- `mtf_5m_risk_on_score_20 >= 0.35`

Ranking and exits:

- expected-R ridge ranking;
- top `3` per decision time;
- validation-selected expected-R threshold `-0.10`;
- stop `0.4%`;
- target `0.8%`;
- horizon timeout `12` bars;
- cost assumption `0.07%` round-trip.

## Stability Artifact

`ct138_no_weak_symbols_no_riskoff_top3` passed all explicit stability gates:

| Gate | Result |
| --- | --- |
| positive OOS expectancy | pass |
| beats rule-only OOS | pass |
| minimum trade count | pass (`118 >= 100`) |
| drawdown within limit | pass (`1.91% <= 8.00%`) |
| symbol breadth | pass (`85.71%` positive symbols) |
| session breadth | pass (`66.67%` positive sessions) |
| lucky-day concentration | pass (`48.17% <= 75.00%`) |
| nearby sensitivity | pass (`100.00%` positive variants) |

Symbol slices:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| SOLUSDT | `15` | `1.0250` |
| AVAXUSDT | `7` | `0.9679` |
| ADAUSDT | `10` | `0.6250` |
| SUIUSDT | `9` | `0.4917` |
| TONUSDT | `27` | `0.3806` |
| ICPUSDT | `37` | `0.2845` |
| DOTUSDT | `13` | `-0.0212` |

Session slices:

| Session | Trades | Avg R |
| --- | ---: | ---: |
| Asia | `23` | `-0.0011` |
| Europe | `26` | `0.4404` |
| US | `69` | `0.6076` |

Risk remains:

- Asia is basically flat and slightly negative;
- DOT is slightly negative;
- only `118` OOS trades, so the paper gate still matters;
- validation selected a negative expected-R threshold, so the model is still better understood as a
  ranking model than a calibrated absolute expectancy estimator.

## Interpretation

The refinement is meaningful because it improved drawdown sharply without collapsing trade count
below the `100` gate. It also improved expectancy versus CT-130 base.

What improved:

- average R: `0.2620 -> 0.4521`
- max DD: `7.20% -> 1.91%`
- profit factor: `1.4279 -> 1.8408`
- weak BTC/ETH/XRP/ATOM exposure removed from candidate selection;
- risk-off conditions filtered out.

What did not become solved:

- this is still backtest research evidence;
- forward paper evidence is still `0` closed trades for this refined candidate;
- the active CT-137 collector currently tracks the CT-130/CT-132 base pack, not this refinement;
- no live trading approval exists.

## Next Step

CT-139 was created to prepare the refined paper pack. That issue should decide whether to run the
CT-138 refinement as a second scheduled paper stream or replace the CT-137 base stream after explicit
review.

CT-113 remains open until a candidate passes forward paper gates or the research path is explicitly
paused or re-scoped.
