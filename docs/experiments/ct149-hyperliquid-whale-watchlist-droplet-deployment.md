# CT-149 Hyperliquid Whale Watchlist Droplet Deployment

Date: 2026-05-27

Issue: CT-149

Epic: CT-113

## Decision

Deploy the CT-134 Hyperliquid whale watchlist collector as a lightweight forward-only data stream on
the `Paper-trading-test` droplet. This is data collection only. It is not a paper-trading candidate,
not a live-trading signal, and not an approval to trade.

## Scope

Target:

- droplet: `Paper-trading-test`
- host: `209.38.188.101`
- path: `/opt/crypto-trade-research`

Watchlist:

- config: `configs/ct134-hyperliquid-whale-watchlist.json`
- wallet alias: `eth_50x_note_wallet`
- wallet: `0xf3F496C9486BE5924a93D67e98298733Bb47057c`

Runner:

- script: `scripts/run_ct149_hyperliquid_whale_watchlist_once.sh`
- command: `python -m crypto_trade_research.data.hyperliquid_watchlist`
- mode: one iteration per timer tick
- fills: skipped for frequent polling to avoid repeatedly storing the capped recent fill history
- output: `data/generated/ct134_hyperliquid_whale_watchlist/watchlist_run.json`

## Rationale

CT-131 found that order-book, OI, and liquidation heatmap signals cannot be added safely to the
six-month model without point-in-time historical data. CT-133/CT-134 made the watched-wallet path
feasible as forward-collected public evidence. CT-149 turns that collector on so we can build a
real timestamped history instead of relying on screenshots.

## Deployment Verification

Installed systemd units on the droplet:

- service: `ct149-hyperliquid-whale-watchlist.service`
- timer: `ct149-hyperliquid-whale-watchlist.timer`
- schedule: every `5` minutes via `OnUnitActiveSec=5min`, with `20s` randomized delay

First systemd-managed run:

| Field | Value |
| --- | ---: |
| generated at | `2026-05-27T10:30:58Z` |
| include fills | `false` |
| position rows | `0` |
| fill rows | `0` |
| alerts | `0` |
| warning count | `1` |

Warning:

`0xf3f496c9486be5924a93d67e98298733bb47057c has no open Hyperliquid perp positions at snapshot time`

This is a valid inactive-wallet snapshot, not a collector failure.

Observed generated size after the first run:

- latest timestamped snapshot directory: about `28K`;
- summary directory: about `8K`.

## Safety Boundary

Research-only public API reads:

- no live credentials;
- no order placement or cancellation;
- no leverage or margin changes;
- no runtime trade-state writes;
- no CT-145 strategy changes;
- no working-model or live-trading approval.

## Validation Gate Before Use

Whale features may influence a later paper candidate only after a separate issue proves:

- at least `30` calendar days of forward data;
- meaningful open-position observations, not only inactive-wallet warnings;
- source timestamps are point-in-time and source-available;
- alerts improve decisions versus no-whale baselines after costs;
- follow and fade hypotheses are evaluated separately;
- results are not dominated by a single stale or inactive wallet.
