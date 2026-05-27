# CT-151 Binance Crowding Forward Collector

Date: 2026-05-27

Issue: CT-151

Epic: CT-113

## Decision

Added a research-only Binance USD-M futures open-interest and crowding forward snapshot collector.
This is data collection only. It does not change CT-145 paper-candidate behavior and does not
approve live trading.

## Motivation

CT-131 found that open-interest and long/short crowding are useful external futures context, but
public Binance history is limited to recent windows. To use these fields safely in later research, we
need point-in-time forward snapshots with `source_available_at`, not retrospective joins.

Official public endpoints checked on 2026-05-27:

- `GET /fapi/v1/openInterest`
- `GET /futures/data/openInterestHist`
- `GET /futures/data/globalLongShortAccountRatio`

## Implementation

Added:

- module: `crypto_trade_research.data.binance_crowding`
- CLI: `crypto-trade-collect-binance-crowding`
- config: `configs/ct151-binance-crowding-forward-snapshot.json`
- runner: `scripts/run_ct151_binance_crowding_snapshot_once.sh`
- tests: `tests/test_binance_crowding.py`

The collector writes timestamped snapshot datasets:

- `current_open_interest.parquet`
- `open_interest_hist.parquet`
- `global_long_short_ratio.parquet`
- `manifest.json`

It also writes a latest-run summary:

- `data/generated/ct151_binance_crowding_forward/crowding_run.json`

## Snapshot Universe

Uses the CT-145 / CT-113 context universe:

- `SOLUSDT`
- `SUIUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `ICPUSDT`
- `ATOMUSDT`
- `XRPUSDT`
- `TONUSDT`
- `DOTUSDT`
- `BTCUSDT`
- `ETHUSDT`

## Local One-Shot Result

Command:

```sh
scripts/run_ct151_binance_crowding_snapshot_once.sh
```

Result:

| Field | Value |
| --- | ---: |
| latest generated at | `2026-05-27T10:41:57Z` |
| row count | `33` |
| symbols | `11` |
| warnings | `0` |

The row count is expected: `11` symbols times `3` source tables.

## Droplet Deployment

Installed on `Paper-trading-test` (`209.38.188.101`):

- service: `ct151-binance-crowding-snapshot.service`
- timer: `ct151-binance-crowding-snapshot.timer`
- schedule: every `5` minutes via `OnUnitActiveSec=5min`, with `20s` randomized delay
- path: `/opt/crypto-trade-research`

First systemd-managed run:

| Field | Value |
| --- | ---: |
| latest generated at | `2026-05-27T10:45:17Z` |
| row count | `33` |
| symbols | `11` |
| warnings | `0` |
| service status | `0/SUCCESS` |

Observed generated size after the first run:

- latest timestamped snapshot directory: about `32K`;
- summary directory: about `8K`.

## Safety Boundary

Research-only public REST reads:

- no live credentials;
- no order placement or cancellation;
- no leverage or margin changes;
- no runtime trade-state writes;
- no CT-145 strategy changes;
- no working-model or live-trading approval.

## Validation Before Use

Crowding fields may influence a later paper candidate only after a separate validation issue proves:

- point-in-time source availability;
- enough forward history for the intended horizon;
- comparison against no-crowding and funding-only baselines;
- positive effect on avg R, drawdown, and abstention quality after costs;
- no single-symbol or single-day dominance.
