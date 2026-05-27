# CT-160 Binance Liquidations Forward Collector

Date: 2026-05-27

Issue: CT-160

Epic: CT-113

Status: research-only collector, not a trading model

## Objective

Test whether liquidation bursts can become useful external point-in-time evidence for CT-113. This
addresses the user hypothesis that liquidation clusters may reveal forced selling/buying pressure or
market-maker target zones.

## Data Source

- Source: Binance USD-M Futures public websocket `!forceOrder@arr`
- Routed endpoint: `wss://fstream.binance.com/market/ws/!forceOrder@arr`
- Official websocket connection docs checked on 2026-05-27:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Connect>
- Official all-market liquidation stream docs checked on 2026-05-27:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams>
- Config: `configs/ct160-binance-liquidations-forward-snapshot.json`
- Runner: `scripts/run_ct160_binance_liquidation_snapshot_once.sh`
- Output prefix: `data/generated/ct160_binance_liquidations_forward`
- Universe: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`,
  `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`

Important source limitation: Binance documents this stream as a snapshot stream. It pushes only the
largest liquidation order per symbol within each 1000ms interval, and pushes nothing when no
liquidation happens in that interval. So this is not a complete liquidation tape or a full
liquidation heatmap.

## Schema

Each run writes:

- `clean/liquidations.parquet`
- `manifest.json`
- latest compact run summary at
  `data/generated/ct160_binance_liquidations_forward/liquidation_run.json`

Normalized fields include event time, symbol, side, order type, time in force, quantity, price,
average price, filled quantity, trade time, notional, and inferred liquidation direction:

- `SELL` means forced sell flow, interpreted as `long_liquidation`;
- `BUY` means forced buy flow, interpreted as `short_liquidation`.

Empty capture windows are valid heartbeat snapshots. A zero-row run means no watched-symbol
liquidation event arrived during the bounded capture window, not collector failure.

## Research Use

This source can support later features such as:

- liquidation notional over recent 5m/15m windows;
- long-vs-short liquidation imbalance;
- liquidation bursts near CT-145/CT-156 candidate timestamps;
- post-liquidation continuation vs reversal behavior;
- interaction with crowding, funding, and order-book imbalance.

It should not be used directly as a trade trigger. A liquidation print is after-the-fact forced
flow, not advance knowledge of where future liquidations will happen.

## Initial Decision

CT-160 is a data-expansion task. It keeps CT-113 open and creates forward-only evidence for a later
liquidation-conditioned validation matrix.

## Initial Smoke Result

Local websocket smoke on 2026-05-27:

- manifest:
  `data/generated/ct160_binance_liquidations_forward_20260527T140653Z/manifest.json`
- capture window: 70 seconds
- all-market source events: 35
- filtered-out non-universe events: 32
- watched-universe rows: 3
- warnings: none

This confirms the stream is live and usable for forward evidence collection. The low watched-universe
row count is expected because Binance publishes only snapshot liquidation events and the configured
universe is a subset of all USD-M symbols.

Droplet smoke on 2026-05-27:

- manifest:
  `data/generated/ct160_binance_liquidations_forward_20260527T140848Z/manifest.json`
- all-market source events: 21
- filtered-out non-universe events: 20
- watched-universe rows: 1
- warnings: none

Droplet deployment:

- service: `ct160-binance-liquidation-snapshot.service`
- timer: `ct160-binance-liquidation-snapshot.timer`
- cadence: every 5 minutes with randomized delay
- first systemd run: `Result=success`, `ExecMainStatus=0`
- timer state: `active/waiting`
- unified stream health: `overall_status=ok`, latest CT-160 `row_count=4`, warnings none
