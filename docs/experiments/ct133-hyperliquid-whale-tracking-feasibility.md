# CT-133 Hyperliquid Whale Tracking Feasibility

Date: 2026-05-27

Issue: CT-133

Epic: CT-113

## Decision

Feasible as a forward-collected research signal, not immediately backtestable in CT-113.

The wallet from the note can be tracked through Hyperliquid public information endpoints, and a
research-only collector was added. However, this is not a paper-trading or live-trading signal yet:
we do not have a six-month point-in-time whale-position history aligned to the current candle and
funding datasets.

No live order placement was touched.

## Wallet Checked

Address from screenshot/note:

`0xf3F496C9486BE5924a93D67e98298733Bb47057c`

Screenshot observation:

- venue appears to be Hyperliquid perps;
- ETH long;
- roughly `50x` cross leverage;
- very large notional ETH exposure;
- liquidation price close to entry/mark, implying high forced-flow risk.

Live API check on 2026-05-27:

- current `clearinghouseState` account value: `0.0`;
- current open perp positions: `0`;
- current one-off snapshot warning:
  `has no open Hyperliquid perp positions at snapshot time`;
- `userFills` returned `2000` recent fills, mostly around 2025-03-16 to 2025-03-22 for this
  address, so the address had visible trade history but is not currently in the shown ETH position.

## Data Sources

Official Hyperliquid docs used:

- info endpoint:
  `https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint`
- perpetuals info endpoint:
  `https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals`
- rate limits:
  `https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits`

Relevant endpoint support:

- `clearinghouseState` can retrieve a user's perpetual account summary, including open positions and
  margin state;
- `openOrders` / `frontendOpenOrders` can retrieve visible open orders for a wallet;
- `userFills` returns at most `2000` most recent fills;
- `userFillsByTime` returns at most `2000` fills per response and only the `10000` most recent fills
  are available;
- rate limits are public and need to be respected for any watchlist polling.

## Implementation

Added research-only Hyperliquid watched-wallet snapshot ingestion:

- module: `crypto_trade_research.data.hyperliquid_whales`
- CLI: `crypto-trade-ingest-hyperliquid-whales`
- current-position source: `clearinghouseState`
- fill source: `userFills` or `userFillsByTime`
- outputs:
  - raw wallet snapshot JSON;
  - normalized positions Parquet;
  - normalized fills Parquet;
  - manifest with source metadata, hashes, row counts, and warnings.

The collector normalizes:

- wallet address;
- symbol;
- side;
- position size;
- notional USD;
- entry price;
- mark price;
- unrealized PnL;
- return on equity;
- leverage type/value;
- liquidation price;
- fills with price, size, notional, direction, fee, order id, trade id, and hash.

One-off generated snapshot:

- dataset: `ct133_hyperliquid_whale_snapshot`
- position rows: `0`
- fill rows: `2000`
- warning: watched wallet has no open perp positions at snapshot time.

Generated artifacts under `data/generated/` are ignored and were not committed.

## Signal Thesis

This is a copy-flow / forced-flow signal, not a classic technical indicator.

Potential edge:

- very large high-leverage positions can create predictable forced-flow zones near liquidation;
- repeated profitable wallets may reveal informed positioning before public market reaction;
- a whale's position open/scale/close behavior may help classify whether ETH/BTC risk is squeeze,
  continuation, or fade-prone.

Potential uses:

- alert-only context for paper trading;
- market-regime feature: `tracked_whale_net_notional_usd`;
- risk feature: `distance_to_tracked_whale_liquidation_bps`;
- event feature: `tracked_whale_new_position_notional_zscore`;
- filter: avoid shorting while a known high-conviction whale is long unless price is near
  liquidation/failure;
- separate strategy: follow/fade after whale opens, scales, closes, or gets near liquidation.

## Why We Cannot Use It Directly Yet

Current CT-113 datasets are Binance USD-M futures candles and funding rates. Hyperliquid watched
wallet data is not present historically.

Immediate model inclusion would be unsafe because:

- the screenshot is a stale anecdote, not a point-in-time dataset;
- the checked wallet has no current open position;
- `userFills` history is capped and does not provide full six-month position snapshots;
- position state must be polled or streamed forward to know what was visible at each decision time;
- Hyperliquid symbols can be UI-remapped, e.g. asset IDs like `@142`, so mapping has to be explicit;
- one whale may stop trading, change address, or become adversarial/noisy.

## Recommended Forward Collector Rules

Watchlist:

- start with the screenshot address;
- add only wallets with repeatable public evidence and label provenance;
- avoid overfitting to a single viral screenshot.

Polling:

- `clearinghouseState`: every `30-60` seconds for watched wallets;
- `frontendOpenOrders`: every `30-60` seconds if order-wall/order-intent research is needed;
- `userFillsByTime`: incremental catch-up every few minutes;
- store `source_available_at` and API response time.

Signal thresholds for research only:

- open position notional `>= $5M`;
- leverage `>= 10x`;
- liquidation distance `<= 3%` for forced-flow alerts;
- new/changed position notional delta `>= $1M`;
- same-direction add within `15m`;
- close/reverse event after drawdown or near liquidation.

Validation:

- minimum `30` days of forward data before use in paper trading;
- compare against no-whale baseline and CT-130 funding candidate;
- measure whether alerts improve avg R, drawdown, and no-trade filtering;
- evaluate follow and fade separately;
- never assume the trader is "insider" without evidence; treat it as observed public flow only.

## Conclusion

The idea is useful and implementable as a forward-collected research input. It cannot be promoted to
the current CT-130/CT-132 paper candidate until we collect enough point-in-time whale data and prove
it improves decisions.

CT-113 remains open. No live trading approval.
