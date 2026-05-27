# CT-141 DOT Exclusion Sensitivity

Date: 2026-05-27

Issue: CT-141

Epic: CT-113

## Decision

CT-141 strengthens the CT-138 refined negative-funding candidate. Removing `DOTUSDT` from candidate
selection did not break the edge. The best no-DOT variant increased OOS trade count above the
minimum gate while keeping expectancy positive and drawdown low.

Best no-DOT row:

- candidate: `ct141_no_dot_top3`
- side: long
- horizon: `12` bars
- strategy: expected-R ridge top3 with existing risk controls
- candidate symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `TONUSDT`
- OOS trades: `269`
- average R after costs: `0.3306`
- rule-only average R: `-0.4970`
- max drawdown: `2.32%`
- profit factor: `1.5648`
- selected probability threshold: `0.55`
- selected expected-R threshold: `-0.20`
- external stability artifact status: `pass`

This is still research evidence only. It is not live-trading approval. The next step is a separate
paper-pack update issue for the no-DOT variant so it can collect fresh forward evidence without
silently changing the active CT-139 stream.

## Thesis

CT-138 passed stability but had a weak `DOTUSDT` symbol slice and only `118` OOS trades. CT-141
tested whether removing DOT would preserve the negative-funding / risk-on long edge while improving
trade count and reducing single-symbol dependence.

## Data

Same six-month data as CT-138:

- candle dataset: `ct121_six_month_core_futures_dataset`
- funding dataset: `ct128_six_month_funding_rate_dataset`
- train end: `2026-03-25T00:00:00Z`
- validation end: `2026-04-25T00:00:00Z`
- test end: `2026-05-25T00:00:00Z`

The full CT-130/CT-138 universe remains available for BTC/ETH context and breadth features. Only
candidate entries were restricted by `candidate_setup.symbols`.

## Implementation

Added configs:

- `configs/ct141-dot-exclusion-sensitivity-matrix.json`
- `configs/ct141-no-dot-detailed-stability-matrix.json`

Also hardened the CT-140 cache writer so large parquet artifacts are written in `50,000` row chunks.
The cold CT-141 run wrote a `1.2 GB` feature cache and the detailed follow-up confirmed feature and
candidate-label cache hits.

Generated artifacts:

- `data/generated/ct141_dot_exclusion_sensitivity_matrix/leaderboard.json`
- `data/generated/ct141_dot_exclusion_sensitivity_matrix/leaderboard.md`
- `data/generated/ct141_no_dot_top3_detailed/baseline_report.json`
- `data/generated/ct141_no_dot_top3_detailed/stability_report.json`

Generated artifacts are not committed.

## Matrix Results

| Experiment | Avg R | Rule Avg R | Trades | Max DD | Profit Factor | Selected E[R] | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CT-138 recheck | `0.4521` | `-0.5104` | `118` | `1.91%` | `1.8408` | `-0.10` | supports |
| no DOT | `0.3306` | `-0.4970` | `269` | `2.32%` | `1.5648` | `-0.20` | best for paper update |
| no DOT, risk-on `0.30` | `0.2857` | `-0.4967` | `267` | `1.86%` | `1.4738` | `-0.20` | supports |
| no DOT, risk-on `0.45` | `0.3581` | `-0.4736` | `272` | `2.52%` | `1.6233` | `-0.20` | supports |

All no-DOT sensitivity rows stayed positive, beat rule-only/no-trade baselines, met the `>=100` OOS
trade gate, and kept drawdown below the `8%` gate.

## Top-N Evidence

For `ct141_no_dot_top3`:

| Strategy | Trades | Avg R | Max DD | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| expected-R top1 | `228` | `0.2461` | `2.28%` | `1.3979` |
| expected-R top2 | `254` | `0.2659` | `2.46%` | `1.4355` |
| expected-R top3 | `269` | `0.3306` | `2.32%` | `1.5648` |
| expected-R top5 | `268` | `0.2914` | `2.41%` | `1.4852` |

The top-N curve is not a single sharp optimum. Top3 was best in this run, while top1/top2/top5 all
remained positive.

## Stability Artifact

`ct141_no_dot_top3` passed all explicit stability gates when evaluated with detailed trade output:

| Gate | Result |
| --- | --- |
| positive OOS expectancy | pass |
| beats rule-only OOS | pass |
| minimum trade count | pass (`269 >= 100`) |
| drawdown within limit | pass (`2.32% <= 8.00%`) |
| symbol breadth | pass (`83.33%` positive symbols) |
| session breadth | pass (`66.67%` positive sessions) |
| lucky-day concentration | pass (`39.28% <= 75.00%`) |
| nearby sensitivity | pass (`100.00%` positive variants) |

Symbol slices:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| ADAUSDT | `43` | `0.7087` |
| SOLUSDT | `31` | `0.5669` |
| SUIUSDT | `28` | `0.4321` |
| AVAXUSDT | `24` | `0.3250` |
| ICPUSDT | `92` | `0.2598` |
| TONUSDT | `51` | `-0.0574` |

Session slices:

| Session | Trades | Avg R |
| --- | ---: | ---: |
| Asia | `78` | `0.1327` |
| Europe | `55` | `-0.0295` |
| US | `136` | `0.5897` |

## Interpretation

This is a useful improvement over CT-138 because the candidate no longer depends on DOT and has more
than twice the OOS trade count. The remaining weak slices are TON and Europe session, but neither is
bad enough to fail breadth gates.

What improved versus CT-138:

- OOS trades: `118 -> 269`
- DOT dependency removed
- symbol breadth remains positive across `5/6` candidate symbols
- nearby no-DOT risk thresholds all stayed positive

What became weaker versus CT-138:

- average R fell from `0.4521` to `0.3306`
- max DD rose from `1.91%` to `2.32%`
- selected expected-R threshold moved from `-0.10` to `-0.20`, so this is still best understood as a
  ranking model, not calibrated absolute expectancy.

## Next Step

Created CT-142 to prepare a no-DOT paper pack and fresh forward-paper collector. Do not approve live
trading from this backtest. CT-113 remains open until the candidate passes forward paper gates or the
research path is explicitly paused or re-scoped.
