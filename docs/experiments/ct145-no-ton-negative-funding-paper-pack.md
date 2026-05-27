# CT-145 No-TON Negative-Funding Paper Pack

Date: 2026-05-27

Issue: CT-145

Epic: CT-113

## Decision

Prepared a separate research-only paper pack for the CT-144 no-TON negative-funding candidate and
prepared it for hourly forward-paper collection on a small DigitalOcean droplet. This does not
approve live trading and does not complete CT-113.

## Candidate

Pack:

- `ct145_no_ton_negative_funding_paper_pack`
- candidate: `ct144_no_ton`
- model artifact: `ct144_no_ton_detailed`
- feature set: `features.ct138.regime-symbol-refinement.v1`
- expected-R model: available
- selected expected-R threshold: `-0.20`
- selected probability threshold: `0.55`

Historical evidence from CT-144:

| Metric | Value |
| --- | ---: |
| OOS trades | `275` |
| Avg R after costs | `0.3959` |
| Rule-only Avg R | `-0.4591` |
| Max DD | `1.60%` |
| Profit factor | `1.7073` |
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

`TONUSDT` remains available only as a context/breadth symbol. It must not be a candidate symbol.

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

- `configs/ct145-no-ton-negative-funding-paper-pack.json`
- `configs/ct145-no-ton-negative-funding-paper-collector.json`
- `configs/ct145-no-ton-negative-funding-paper-monitoring.json`
- `configs/ct145-no-ton-forward-paper-run.json`

Added runner script:

- `scripts/run_ct145_forward_paper_once.sh`

Generated artifacts:

- `data/generated/ct145_no_ton_negative_funding_paper_pack/pack_manifest.json`
- `data/generated/ct145_no_ton_negative_funding_paper_collector/signals.json`
- `data/generated/ct145_no_ton_negative_funding_paper_collector/ledger.json`
- `data/generated/ct145_no_ton_negative_funding_paper_collector/monitoring_report.json`
- `data/generated/ct145_no_ton_negative_funding_forward_paper/forward_run.json`
- `data/generated/ct145_no_ton_negative_funding_forward_paper/monitoring_report.json`

Generated artifacts are not committed.

## Dry-Run Result

Historical dry-run collector result:

| Field | Value |
| --- | --- |
| mode | `historical_dry_run` |
| decision time | `2026-05-24T10:28:00Z` |
| candidate count | `1` |
| signal count | `1` |
| take count | `1` |
| ledger entries | `1` |
| take symbol | `ICPUSDT` |
| expected R | `-0.1846` |
| selected threshold | `-0.20` |
| probability | `0.5818` |
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
| decision time | `2026-05-27T09:20:00Z` |
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

## Droplet Runner Plan

Target droplet:

- name: `Paper-trading-test`
- reserved IP: `209.38.188.101`
- Ubuntu 24.04
- size: `1 vCPU / 512MB RAM / 10GB disk`

The droplet is too small for six-month backtests or full feature-cache materialization. It should
run only the lightweight fresh forward-paper collector:

- no Docker;
- no live exchange credentials;
- no historical training dataset;
- local `.venv` with the base research package dependency set;
- copied `pack_manifest.json` and `model_artifact.json`;
- `systemd` hourly timer running `scripts/run_ct145_forward_paper_once.sh`.

## Droplet Deployment

Deployment target:

- host: `209.38.188.101`
- path: `/opt/crypto-trade-research`
- timer: `ct145-forward-paper.timer`
- service: `ct145-forward-paper.service`
- schedule: hourly, persistent, with up to `30s` randomized delay
- swap: `1GB` `/swapfile`

First systemd-managed run on the droplet completed successfully:

| Field | Value |
| --- | ---: |
| created at | `2026-05-27T09:28:58Z` |
| decision time | `2026-05-27T09:28:00Z` |
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

The no-trade result is valid for a fresh forward tick. It means the current public market snapshot
did not pass the entry filters; it is not a rejection of the candidate.

Observed droplet headroom after installation and the first service run:

- memory available: about `298MiB`;
- swap used: about `5MiB` of `1GB`;
- root disk used: about `3.2GB` of `8.7GB`.

Deployment note: avoid broad `models/` excludes when syncing the research package. The package source
contains `src/crypto_trade_research/models/`, which is required by the paper runner.

## Safety Boundary

Research-only:

- no live trading approval;
- no order placement or cancellation;
- no leverage or margin changes;
- no runtime trade-state writes;
- no secrets or authenticated exchange calls.

The pack manifest explicitly sets `live_order_authority` to `false` and only allows signal logging,
paper fills, and paper skips.
