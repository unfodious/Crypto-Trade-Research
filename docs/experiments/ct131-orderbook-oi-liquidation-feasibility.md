# CT-131 Order-Book, OI, And Liquidation Data Feasibility

Date: 2026-05-27

Issue: CT-131

Epic: CT-113

## Decision

Rejected for immediate CT-113 model inclusion. The ideas are valid market-microstructure and
crowding hypotheses, but the current research dataset does not contain point-in-time historical
order-book depth, open-interest crowding, or liquidation-event history. Adding these signals without
historical provenance would create a look-ahead or anecdotal selection risk.

The only immediately applied proxy is CT-128 funding-rate crowding. That branch found a promising
long negative-funding pocket, but it is not paper-trading approved yet. CT-130 remains the next
actionable validation issue for that candidate.

CT-131 should therefore be treated as a data-acquisition and feasibility branch:

- keep CT-113 open;
- do not touch live trading or runtime order placement;
- do not add order-book or liquidation heatmap features to the model until historical data exists;
- prefer a forward collector or paid historical source before another matrix.

## Researched Data Sources

Official Binance USD-M futures sources checked:

- order book REST: `https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book`
- partial order-book depth stream:
  `https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams`
- open-interest statistics:
  `https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics`
- all-market liquidation stream:
  `https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams`

Key constraints:

- REST order book gives the current book snapshot, not a six-month historical book.
- Partial book streams can collect top-of-book history from now onward, but cannot reconstruct the
  past unless an archive already exists.
- Binance open-interest statistics are useful for crowding, but the public historical endpoint only
  exposes the latest one month.
- The all-market liquidation stream publishes liquidation snapshots forward-only. It is not a
  historical liquidation heatmap.

## Hypothesis 1: Unusual Buy Walls

Thesis: an unusually large passive bid near or below the market may indicate support, absorption, a
liquidity magnet, or a spoofing attempt. If the wall persists and price reacts before it is pulled,
it may help identify asymmetric long entries or no-short zones.

Useful future features:

- bid-wall notional by distance from mid price;
- wall z-score versus recent symbol depth;
- wall distance in basis points and ATR units;
- wall persistence in seconds;
- pull/cancel ratio after price approaches the wall;
- bid/ask imbalance at top 5, 10, and 20 levels;
- interaction with realized volatility and funding regime.

Main risks:

- spoofing: visible size can disappear before execution;
- latency: historical snapshots must include source availability and stream lag;
- capacity and storage: depth streams are much larger than candle/funding data;
- execution realism: a backtest must assume fills only after the wall was observable.

Status: feasible only after collecting or buying historical depth data.

## Hypothesis 2: Huge Short Positions

Thesis: a rapid rise in short crowding can precede either continuation down or a forced short-covering
reversal. The direction depends on whether shorts are early and correct, or late and vulnerable.

Potential signals:

- open-interest growth with price falling;
- open-interest growth with negative funding;
- top-trader or global long/short ratio extremes;
- taker sell pressure versus funding;
- BTC/ETH market regime filter.

Current application:

- CT-128 already tested the most accessible proxy: funding-rate crowding.
- The strongest CT-128 candidate was long negative-funding expected-R top3:
  - OOS trades: `101`
  - average R after costs: `0.1616`
  - max drawdown: `7.20%`
  - rule-only average R: `-0.6642`

That is promising, but not enough to call it a working model. It needs CT-130 stability validation
before any paper-trading plan.

Status: partially applied through funding; direct OI crowding needs historical OI/ratio data beyond
the current public one-month window.

## Hypothesis 3: Liquidation Heatmap

Thesis: liquidation clusters can act as magnets, acceleration zones, or post-squeeze reversal zones.
The idea is reasonable because forced exits create predictable order flow when price reaches the
cluster.

Important distinction:

- liquidation events are exchange-observed forced orders after liquidation happens;
- liquidation heatmaps are usually estimates of where liquidations may happen, based on open
  interest, leverage assumptions, position distribution, and price levels.

The Binance all-market liquidation stream can collect realized liquidation events from now onward.
It does not provide a six-month historical heatmap, and it only emits the largest liquidation order
per symbol within a one-second interval.

Useful future features:

- liquidation notional by symbol/side/time bucket;
- liquidation burst z-score;
- distance from current price to estimated liquidation clusters;
- post-liquidation continuation versus reversal labels;
- interaction with funding, open-interest growth, and BTC/ETH shock regime.

Status: not feasible for current six-month backtest without a vendor archive or internal forward
collection. A heatmap requires either a paid data source or a separately validated estimator.

## Recommended Next Work

Immediate CT-113 path:

1. Continue CT-130 and validate the CT-128 negative-funding long candidate.
2. Do not promote any order-book, OI, or liquidation signal before historical data exists.
3. Keep using backtests as research evidence only.

Future data branch:

1. Add a forward-only market-microstructure collector for Binance USD-M futures:
   - partial or diff depth streams;
   - periodic open-interest snapshots while available;
   - all-market liquidation stream;
   - source availability timestamps and stream lag.
2. Evaluate paid historical sources for depth/OI/liquidation data if six-month validation is required
   immediately.
3. Once data exists, create a separate CT issue for an order-flow/crowding matrix rather than mixing
   it into CT-130.

Minimum data contract for any future collector:

- `symbol`
- `event_time`
- `source_available_at`
- `source`
- `stream_lag_ms`
- `side`
- `price`
- `quantity`
- `notional`
- `distance_from_mid_bps`
- source-specific update id or sequence id

## Conclusion

These ideas are not discarded. They are better categorized as order-flow/crowding research, not
technical-indicator tuning. The most practical near-term path is to finish CT-130 on the funding
candidate, then add a data acquisition issue for order-book/OI/liquidation history if we want this
class of edge in CT-113.
