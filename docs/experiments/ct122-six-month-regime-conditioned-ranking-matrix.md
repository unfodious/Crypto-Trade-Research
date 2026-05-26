# CT-122 Six-Month Regime-Conditioned Ranking Matrix

Date: 2026-05-26

Issue: CT-122

Epic: CT-113

## Decision

Rejected. CT-122 made the six-month matrix runnable and produced enough OOS trades for the strict
h12 setup variants, but no candidate met the promotion gates. The h12 long breakout pocket from
CT-121 did not survive the wider six-month window.

Backtests remain research evidence only. No paper-trading pack is approved.

## What Changed

CT-121 proved that six-month data was available but the full-universe runner was killed during
label generation. CT-122 added a memory-safe experiment path:

- `memory.label_generation_mode=candidate_only`
- generate full point-in-time features for the configured universe,
- derive labels only for rows matching the predeclared `candidate_setup`,
- write sparse candidate feature/label artifacts for large runs,
- cache candidate labels across batch rows that share the same candidate setup,
- add a reusable local Docker QA image target to avoid repeated clean-container `apt`/`pip` setup.

Calibration was also tightened so zero-trade validation thresholds are reported but cannot win over
thresholds with actual validation trades.

## Data

Dataset: `ct121_six_month_core_futures_dataset`

Rows: `2,867,040`

Window:

- min close time: `2025-11-25T00:01:00Z`
- max close time: `2026-05-25T00:00:00Z`

Symbols:

`SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`, `TONUSDT`,
`DOTUSDT`, `BTCUSDT`, `ETHUSDT`

BTC/ETH are both part of the traded universe and reference context features for the full universe.
The BTC/ETH regime rows are not BTC/ETH-only training runs.

Splits:

- train end: `2026-03-25T00:00:00Z`
- validation end: `2026-04-25T00:00:00Z`
- test end: `2026-05-25T00:00:00Z`

## Matrix

Config:

- `configs/ct122-h12-memory-safe-six-month-base.json`
- `configs/ct122-six-month-regime-conditioned-ranking-matrix.json`

Predeclared variants:

- strict h12 candidate, unbounded
- strict h12 top 1, 2, 3, 5
- BTC/ETH both above MA top1
- volatility normal top1
- volatility disorderly top1
- BTC/ETH both above MA plus volatility normal top1
- BTC/ETH both above MA plus volatility disorderly top1

Batch result: `10/10` completed, `0` failed.

## Results

| Experiment | Avg R | Rule Avg R | Trades | Max DD | Selected p | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| strict unbounded | -0.4440 | -0.5638 | 3,956 | 99.9967% | 0.55 | reject |
| strict top1 | -0.3298 | -0.5638 | 969 | 84.4485% | 0.55 | reject |
| strict top2 | -0.3127 | -0.5638 | 1,249 | 90.1255% | 0.55 | reject |
| strict top3 | -0.2896 | -0.5638 | 1,396 | 91.0470% | 0.55 | reject |
| strict top5 | -0.2812 | -0.5638 | 1,544 | 93.0141% | 0.55 | reject |
| BTC/ETH above MA top1 | -0.3311 | -0.5301 | 871 | 81.5488% | 0.55 | reject |
| volatility normal top1 | -0.5422 | -0.6388 | 749 | 89.2792% | 0.50 | reject |
| volatility disorderly top1 | -0.3738 | -0.3524 | 161 | 34.5919% | 0.55 | reject |
| BTC/ETH above MA + vol normal top1 | 0.3250 | -0.6156 | 12 | 2.1760% | 0.60 | reject |
| BTC/ETH above MA + vol disorderly top1 | -0.2519 | -0.3311 | 208 | 30.8172% | 0.45 | reject |

The only positive row was `BTC/ETH above MA + vol normal top1`, but it produced only `12` OOS
trades against the `>=100` gate. It is sparse diagnostic evidence, not a paper-trading candidate.

The best row with `>=100` OOS trades by average R was `BTC/ETH above MA + vol disorderly top1`:

- avg R: `-0.2519`
- rule-only avg R: `-0.3311`
- trades: `208`
- max drawdown: `30.82%`

It still failed positive expectancy, drawdown, stability, and paper-plan gates.

## Interpretation

The CT-121 pocket was too narrow and unstable. Six-month evidence increased trade counts, but
ranking and predeclared BTC/ETH/volatility regimes did not recover positive expectancy after costs.
The strict variants improved over rule-only in several cases, but not enough to matter because the
absolute expectancy stayed negative and drawdowns stayed far beyond the `8%` gate.

Simple selection of long breakout signals is not the missing piece. The next hypothesis should
change the risk objective or setup family, not keep tuning thresholds around the same h12 long
breakout pocket.

## Next Hypothesis

Keep CT-113 open. Open a follow-up to test a materially different research idea, such as asymmetric
exit/abstention logic or a short-side risk-off continuation family on the same six-month framework.
