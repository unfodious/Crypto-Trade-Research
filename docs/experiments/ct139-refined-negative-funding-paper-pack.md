# CT-139 Refined Negative-Funding Paper Pack

Date: 2026-05-27

Issue: CT-139

Epic: CT-113

## Decision

Prepared a separate research-only paper pack for the CT-138 refined negative-funding candidate and
started it as a second scheduled forward paper stream. The existing CT-137 base collector was not
replaced.

This does not approve live trading and does not complete CT-113. The refined candidate still needs
forward paper evidence.

## Candidate

Pack:

- `ct139_refined_negative_funding_paper_pack`
- candidate: `ct138_no_weak_symbols_no_riskoff_top3`
- model artifact: `ct138_no_weak_symbols_no_riskoff_top3_detail`
- feature set: `features.ct138.regime-symbol-refinement.v1`
- expected-R model: available
- selected expected-R threshold: `-0.10`
- selected probability threshold: `0.55`

Historical evidence from CT-138:

| Metric | Value |
| --- | ---: |
| OOS trades | `118` |
| Avg R after costs | `0.4521` |
| Rule-only Avg R | `-0.5104` |
| Max DD | `1.91%` |
| Profit factor | `1.8408` |
| Stability status | `pass` |

## Rules

Full context universe remains the CT-130/CT-138 eleven-symbol set so BTC/ETH and breadth context
features are still generated.

Candidate entry symbols:

- `SOLUSDT`
- `SUIUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `ICPUSDT`
- `TONUSDT`
- `DOTUSDT`

Filters:

- `funding_rate <= -0.00002`
- `funding_rate_zscore_20 <= -0.25`
- `close_location >= 0.45`
- `risk_on_score_20 >= 0.35`
- `mtf_5m_risk_on_score_20 >= 0.35`

Ranking and exits:

- expected-R ridge ranking;
- top `3` per decision time;
- stop `0.4%`;
- target `0.8%`;
- horizon timeout `12` closed `1m` bars;
- round-trip cost assumption `0.07%`.

## Files

Added configs:

- `configs/ct139-refined-negative-funding-paper-pack.json`
- `configs/ct139-refined-negative-funding-paper-collector.json`
- `configs/ct139-refined-negative-funding-paper-monitoring.json`
- `configs/ct139-refined-forward-paper-run.json`

Generated artifacts:

- `data/generated/ct139_refined_negative_funding_paper_pack/pack_manifest.json`
- `data/generated/ct139_refined_negative_funding_paper_collector/signals.json`
- `data/generated/ct139_refined_negative_funding_paper_collector/ledger.json`
- `data/generated/ct139_refined_negative_funding_paper_collector/monitoring_report.json`
- `data/generated/ct139_refined_negative_funding_forward_paper/forward_run.json`
- `data/generated/ct139_refined_negative_funding_forward_paper/monitoring_report.json`

Generated artifacts are not committed.

## Dry-Run Result

Historical dry-run collector result:

| Field | Value |
| --- | --- |
| mode | `historical_dry_run` |
| decision time | `2026-05-23T21:22:00Z` |
| candidate count | `5` |
| signal count | `5` |
| take count | `1` |
| ledger entries | `1` |
| take symbol | `DOTUSDT` |
| expected R | `-0.0447` |
| selected threshold | `-0.10` |
| probability | `0.5931` |
| rank | `1` of top `3` |
| historical net R | `-1.1750` |
| paper status | `closed` |
| live order authority | `false` |

The monitoring report correctly fails the paper gate because this is a one-trade historical replay
seed, not forward paper evidence.

## Fresh Forward Run

Fresh public Binance USD-M run result:

| Field | Value |
| --- | ---: |
| decision time | `2026-05-27T07:01:00Z` |
| candle rows | `4,631` |
| funding rows | `300` |
| latest feature rows | `11` |
| candidate count | `0` |
| signal count | `0` |
| paper takes | `0` |
| cumulative trades | `0` |
| open trades | `0` |
| closed trades | `0` |
| monitoring status | `gate_failed` |

This is a valid no-trade state, not a model rejection.

## Schedule

Created a second active hourly Codex app automation:

- id: `ct-139-refined-negative-funding-forward-collection`;
- cadence: hourly;
- workspace: `/Users/unfodious/Projects/crypto-trade-research`;
- scope: rebuild CT-139 pack if needed, run the refined fresh forward collector, and summarize
  cumulative ledger and monitoring status.

The CT-137 base collector remains active. Running both streams preserves a forward comparison
between the base CT-130/CT-132 candidate and the refined CT-138 candidate.

## Safety Boundary

Research-only:

- no live trading approval;
- no order placement or cancellation;
- no leverage or margin changes;
- no runtime trade-state writes;
- no secrets or authenticated exchange calls.

CT-113 remains open until a paper stream passes the forward paper gate or the research path is
explicitly paused or re-scoped.
