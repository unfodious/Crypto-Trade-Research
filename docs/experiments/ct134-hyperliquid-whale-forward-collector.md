# CT-134 Hyperliquid Whale Watchlist Forward Collector

Date: 2026-05-27

Issue: CT-134

Epic: CT-113

## Decision

Forward collector pack prepared. This is research-only infrastructure for collecting point-in-time
whale wallet evidence. It is not a trading model, not a paper-trading signal yet, and not live
trading approval.

CT-133 proved the address can be queried through Hyperliquid public data, but the current CT-113
datasets do not contain historical watched-wallet positions. CT-134 adds the missing forward
collection layer so this idea can become testable after enough data accumulates.

No live trading or order placement code was touched.

## Watchlist

Initial wallet:

- alias: `eth_50x_note_wallet`
- address: `0xf3F496C9486BE5924a93D67e98298733Bb47057c`

Config:

- `configs/ct134-hyperliquid-whale-watchlist.json`

Default thresholds:

- large position notional: `>= $5,000,000`
- leverage: `>= 10x`
- near-liquidation distance: `<= 3%`
- notional delta: `>= $1,000,000`

## Implementation

Added watchlist runner:

- module: `crypto_trade_research.data.hyperliquid_watchlist`
- CLI: `crypto-trade-run-hyperliquid-watchlist`
- input: watchlist JSON config
- output:
  - timestamped raw/clean snapshot datasets;
  - `watchlist_run.json` summary;
  - alerts for large leveraged positions, near-liquidation positions, and notional deltas.

The runner wraps the CT-133 one-shot snapshot collector and adds:

- configurable iterations;
- poll interval;
- first-pass `userFills` plus subsequent `userFillsByTime` incremental catch-up inside a
  multi-iteration run;
- per-iteration snapshot manifests;
- position-to-position notional delta alerts;
- liquidation-distance alerts;
- explicit research-only run metadata.

## Dry Run

Command:

```sh
docker run --rm -v "$PWD":/app -w /app crypto-trade-research-qa:py312 \
  python -m crypto_trade_research.data.hyperliquid_watchlist \
  --config configs/ct134-hyperliquid-whale-watchlist.json \
  --iterations 1 \
  --poll-interval-seconds 0
```

Output:

- run summary: `data/generated/ct134_hyperliquid_whale_watchlist/watchlist_run.json`
- snapshot dataset:
  `data/generated/ct134_hyperliquid_whale_watchlist_20260527T003638Z/manifest.json`

Dry-run result:

- iterations: `1`
- open position rows: `0`
- fill rows: `2000`
- alerts: `0`
- warning:
  `0xf3f496c9486be5924a93d67e98298733bb47057c has no open Hyperliquid perp positions at snapshot time`

The generated data is under `data/generated/`, which is intentionally gitignored.

## Minimum Data Contract

Each snapshot must preserve:

- `source_available_at`
- wallet address and alias
- symbol
- side
- position size
- notional USD
- leverage type/value
- entry price
- mark price
- liquidation price
- liquidation distance
- unrealized PnL
- fills with time, direction, price, size, notional, fees, order id, trade id, and hash

Each watchlist run must preserve:

- config thresholds;
- iteration count;
- snapshot manifest paths;
- warnings;
- alert rows;
- explicit statement that no orders were submitted.

## Operating Runbook

Manual one-shot:

```sh
docker run --rm -v "$PWD":/app -w /app crypto-trade-research-qa:py312 \
  python -m crypto_trade_research.data.hyperliquid_watchlist \
  --config configs/ct134-hyperliquid-whale-watchlist.json \
  --iterations 1 \
  --poll-interval-seconds 0
```

Short local forward collection:

```sh
docker run --rm -v "$PWD":/app -w /app crypto-trade-research-qa:py312 \
  python -m crypto_trade_research.data.hyperliquid_watchlist \
  --config configs/ct134-hyperliquid-whale-watchlist.json \
  --iterations 60 \
  --poll-interval-seconds 60
```

Expected behavior:

- create one timestamped dataset per iteration;
- write or update `data/generated/ct134_hyperliquid_whale_watchlist/watchlist_run.json`;
- produce alerts only when watched wallet state crosses thresholds;
- never submit, cancel, or modify orders.

Failure handling:

- if Hyperliquid rate-limits the collector, pause and resume later;
- if wallet returns no positions, keep the snapshot and warning;
- if symbol remapping appears, document the mapping before using it in a model;
- if generated data grows too quickly, archive or compact old raw JSON after preserving manifests.

## Validation Gate Before Use

This signal may influence CT-132/CT-113 paper decisions only after:

- at least `30` calendar days of forward data;
- at least one watched wallet has meaningful open-position observations;
- alert timestamps are point-in-time and source-available;
- whale alerts are compared against CT-130 candidate decisions;
- follow and fade hypotheses are evaluated separately;
- no-whale baseline remains available;
- drawdown, average R, and no-trade filtering improve after costs;
- signal is not dominated by a single stale or inactive wallet.

Suggested research features after data exists:

- `tracked_whale_net_notional_usd`
- `tracked_whale_side`
- `tracked_whale_position_delta_usd`
- `tracked_whale_leverage`
- `tracked_whale_liquidation_distance_pct`
- `tracked_whale_recent_fill_notional_usd`
- `tracked_whale_alert_count_1h`

## Conclusion

The whale idea now has a concrete forward-collection path. The initial watched wallet is inactive at
the dry-run snapshot, so there is no immediate signal. CT-113 remains open, and CT-132 should not use
whale signals until CT-134 has accumulated enough point-in-time evidence.
