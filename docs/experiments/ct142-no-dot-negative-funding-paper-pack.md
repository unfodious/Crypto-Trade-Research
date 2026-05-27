# CT-142 No-DOT Negative-Funding Paper Pack

Date: 2026-05-27

Issue: CT-142

Epic: CT-113

## Decision

Prepared a separate research-only paper pack for the CT-141 no-DOT negative-funding candidate. This
does not replace the CT-139 stream and does not approve live trading.

The no-DOT candidate is eligible for fresh forward-paper collection because CT-141 passed historical
expectancy, trade-count, drawdown, and stability checks. CT-113 remains open until forward paper
evidence passes the paper gate.

## Candidate

Pack:

- `ct142_no_dot_negative_funding_paper_pack`
- candidate: `ct141_no_dot_top3`
- model artifact: `ct141_no_dot_top3_detailed`
- feature set: `features.ct138.regime-symbol-refinement.v1`
- expected-R model: available
- selected expected-R threshold: `-0.20`
- selected probability threshold: `0.55`

Historical evidence from CT-141:

| Metric | Value |
| --- | ---: |
| OOS trades | `269` |
| Avg R after costs | `0.3306` |
| Rule-only Avg R | `-0.4970` |
| Max DD | `2.32%` |
| Profit factor | `1.5648` |
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

`DOTUSDT` remains available only as a context/breadth symbol. It must not be a candidate symbol.

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

- `configs/ct142-no-dot-negative-funding-paper-pack.json`
- `configs/ct142-no-dot-negative-funding-paper-collector.json`
- `configs/ct142-no-dot-negative-funding-paper-monitoring.json`
- `configs/ct142-no-dot-forward-paper-run.json`

Generated artifacts:

- `data/generated/ct142_no_dot_negative_funding_paper_pack/pack_manifest.json`
- `data/generated/ct142_no_dot_negative_funding_paper_collector/signals.json`
- `data/generated/ct142_no_dot_negative_funding_paper_collector/ledger.json`
- `data/generated/ct142_no_dot_negative_funding_paper_collector/monitoring_report.json`
- `data/generated/ct142_no_dot_negative_funding_forward_paper/forward_run.json`
- `data/generated/ct142_no_dot_negative_funding_forward_paper/monitoring_report.json`

Generated artifacts are not committed.

## Dry-Run Result

Historical dry-run collector result:

| Field | Value |
| --- | --- |
| mode | `historical_dry_run` |
| decision time | `2026-05-23T21:02:00Z` |
| candidate count | `3` |
| signal count | `3` |
| take count | `1` |
| ledger entries | `1` |
| take symbol | `ICPUSDT` |
| expected R | `-0.1733` |
| selected threshold | `-0.20` |
| probability | `0.5827` |
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
| decision time | `2026-05-27T08:10:00Z` |
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

Schedule this as its own hourly forward-paper stream. Do not silently replace CT-139. Running CT-139
and CT-142 side by side preserves a forward comparison between the CT-138 with-DOT refinement and
the CT-141 no-DOT refinement.

## Safety Boundary

Research-only:

- no live trading approval;
- no order placement or cancellation;
- no leverage or margin changes;
- no runtime trade-state writes;
- no secrets or authenticated exchange calls.

The pack manifest explicitly sets `live_order_authority` to `false` and only allows signal logging,
paper fills, and paper skips.
