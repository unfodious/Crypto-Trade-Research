# CT-156 High-Beta+DOT Shadow Paper Pack

Date: 2026-05-27

Issue: CT-156

Epic: CT-113

## Decision

Prepared a separate research-only shadow paper pack for the CT-155 high-beta+DOT negative-funding
candidate. This does not replace CT-145, does not approve live trading, and does not complete CT-113.

CT-145 remains the primary active paper stream. CT-156 is a parallel comparison stream.

## Candidate

Pack:

- `ct156_high_beta_dot_shadow_paper_pack`
- candidate: `ct155_high_beta_plus_dot`
- model artifact: `ct155_high_beta_plus_dot_detailed`
- feature set: `features.ct138.regime-symbol-refinement.v1`
- expected-R model: available
- selected expected-R threshold: `-0.10`
- selected probability threshold: `0.55`

Historical evidence from CT-155:

| Metric | Value |
| --- | ---: |
| OOS trades | `106` |
| Avg R after costs | `0.4665` |
| Rule-only Avg R | `-0.4843` |
| Max DD | `1.47%` |
| Profit factor | `1.8768` |
| Stability status | `pass` |

Important caution: `DOTUSDT` was negative as an individual historical slice (`9` trades, `-0.8417`
avg R), so CT-156 must be monitored as a shadow stream rather than silently promoted over CT-145.

## Rules

Full context universe remains the CT-130/CT-138 eleven-symbol set so BTC/ETH and breadth context
features are still generated.

Candidate entry symbols:

- `SOLUSDT`
- `SUIUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `ICPUSDT`
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

- `configs/ct156-high-beta-dot-shadow-paper-pack.json`
- `configs/ct156-high-beta-dot-shadow-paper-collector.json`
- `configs/ct156-high-beta-dot-shadow-paper-monitoring.json`
- `configs/ct156-high-beta-dot-forward-paper-run.json`

Added runner script:

- `scripts/run_ct156_forward_paper_once.sh`

Updated health summary:

- `crypto-trade-research-stream-health` now includes `ct156_shadow_forward_paper`.

Generated artifacts:

- `data/generated/ct156_high_beta_dot_shadow_paper_pack/pack_manifest.json`
- `data/generated/ct156_high_beta_dot_shadow_paper_collector/signals.json`
- `data/generated/ct156_high_beta_dot_shadow_paper_collector/ledger.json`
- `data/generated/ct156_high_beta_dot_shadow_paper_collector/monitoring_report.json`
- `data/generated/ct156_high_beta_dot_shadow_forward_paper/forward_run.json`
- `data/generated/ct156_high_beta_dot_shadow_forward_paper/monitoring_report.json`

Generated artifacts are not committed.

## Dry-Run Result

Historical dry-run collector result:

| Field | Value |
| --- | --- |
| mode | `historical_dry_run` |
| decision time | `2026-05-23T21:22:00Z` |
| candidate count | `4` |
| signal count | `4` |
| take count | `1` |
| ledger entries | `1` |
| monitoring status | `gate_failed` |

The monitoring report correctly fails the paper gate because this is a one-trade historical replay
seed, not forward paper evidence.

## Fresh Forward Run

Fresh public Binance USD-M run result:

| Field | Value |
| --- | ---: |
| decision time | `2026-05-27T13:36:00Z` |
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

## Droplet Plan

Deploy as a separate timer on `Paper-trading-test` (`209.38.188.101`):

- service: `ct156-forward-paper.service`
- timer: `ct156-forward-paper.timer`
- schedule: hourly, offset from CT-145 to avoid simultaneous fetch bursts;
- path: `/opt/crypto-trade-research`

The CT-145 timer must remain unchanged.

## Droplet Deployment

Installed on `Paper-trading-test` (`209.38.188.101`):

- service: `ct156-forward-paper.service`
- timer: `ct156-forward-paper.timer`
- schedule: hourly at minute `12`, with `30s` randomized delay
- path: `/opt/crypto-trade-research`

First systemd-managed run:

| Field | Value |
| --- | ---: |
| service result | `success` |
| exec status | `0` |
| decision time | `2026-05-27T13:39:00Z` |
| candle rows | `4,631` |
| funding rows | `300` |
| latest feature rows | `11` |
| candidate count | `0` |
| signal count | `0` |
| paper takes | `0` |
| cumulative trades | `0` |
| open trades | `0` |
| closed trades | `0` |

Timer check:

- `ct145-forward-paper.timer`: active, next run at minute `00`;
- `ct156-forward-paper.timer`: active, next run at minute `12`.

The unified health summary reported `overall_status=ok` and no health warnings after deployment.

Created CT-157 to monitor this shadow stream daily.

## Safety Boundary

Research-only:

- no live trading approval;
- no order placement or cancellation;
- no leverage or margin changes;
- no runtime trade-state writes;
- no secrets or authenticated exchange calls.

The pack manifest explicitly sets `live_order_authority` to `false` and only allows signal logging,
paper fills, and paper skips.
