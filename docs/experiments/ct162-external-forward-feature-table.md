# CT-162 External Forward Feature Table

Date: 2026-05-27

Issue: CT-162

Epic: CT-113

Status: research-only feature preparation, not a trading model

## Objective

Turn the new external forward streams into a single point-in-time feature table that future CT-113
validation matrices can consume.

Input streams:

- CT-151/153 Binance crowding snapshots;
- CT-158 Binance order-book depth snapshots;
- CT-160 Binance force-liquidation snapshots.

## Command

```sh
scripts/run_ct162_external_forward_features_once.sh
```

Equivalent installed entrypoint:

```sh
crypto-trade-build-external-forward-features --config configs/ct162-external-forward-features.json
```

## Output

Output prefix:

```text
data/generated/ct162_external_forward_features
```

Each run writes:

- `clean/external_forward_features.parquet`
- `manifest.json`
- latest run summary:
  `data/generated/ct162_external_forward_features/external_forward_features_run.json`

The table is narrow by source family:

- one `crowding` row per symbol per crowding snapshot;
- one `order_book` row per symbol per order-book snapshot;
- one `liquidations` row per symbol per liquidation snapshot.

Liquidation rows are emitted for every configured symbol, including zero-event symbols. This lets a
future as-of join distinguish "no liquidation event in this capture window" from "missing data".

## No-Leakage Rule

All rows carry `source_available_at`.

- Crowding and order-book rows use the source snapshot `generated_at`.
- Liquidation rows use `capture_ended_at`, because the feature summarizes a bounded websocket window
  and cannot be known at the start of that window.

This makes the table safe for later point-in-time joins into candidate decision timestamps.

## Current Feature Families

Crowding:

- current open interest;
- recent open-interest value;
- global long/short ratio;
- top-trader position long/short ratio;
- top-trader account long/short ratio.

Order book:

- spread bps;
- bid/ask notional totals;
- notional imbalance;
- largest visible bid/ask level notional;
- largest visible bid/ask distance from mid.

Liquidations:

- event count;
- total liquidation notional;
- long-liquidation notional;
- short-liquidation notional;
- long-vs-short liquidation notional imbalance.

## Decision

CT-162 prepares forward evidence for future validation. It does not backtest, select, promote, or
approve any trading model. CT-113 remains open until forward evidence supports a paper-trading
candidate or the epic is explicitly paused/re-scoped.

## Initial Smoke Result

Local smoke on 2026-05-27:

- manifest:
  `data/generated/ct162_external_forward_features_20260527T142017Z/manifest.json`
- crowding snapshots: 2
- order-book snapshots: 1
- liquidation snapshots: 1
- feature rows: 44
- symbols: 11
- warnings: none

Droplet smoke on 2026-05-27:

- manifest:
  `data/generated/ct162_external_forward_features_20260527T142149Z/manifest.json`
- crowding snapshots: 42
- order-book snapshots: 7
- liquidation snapshots: 3
- feature rows: 572
- symbols: 11
- warnings: none

Droplet deployment:

- service: `ct162-external-forward-features.service`
- timer: `ct162-external-forward-features.timer`
- cadence: every 15 minutes with randomized delay
- first systemd run: `Result=success`, `ExecMainStatus=0`
- timer state: `active/waiting`
- unified stream health: `overall_status=ok`, CT-162 `row_count=572`
- monitoring issue: CT-163
- daily local automation: `ct-163-external-features-daily-check`
