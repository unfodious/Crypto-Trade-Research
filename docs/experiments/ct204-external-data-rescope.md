# CT-204 external data re-scope for CT-113

Issue: `CT-204`
Epic: `CT-113`

Status: complete; next data-access issue required; no working model claim.

## Question

CT-200 through CT-203 rejected the latest CT-113 branches:

- external OI/session screens did not create enough stable selected-position evidence;
- broad spot rotation stayed too sparse;
- strict no-loss spot exits hid weak entries inside stuck inventory;
- controlled-loss exits removed stuck inventory but collapsed profit factor and monthly return.

CT-204 decides whether there is still a concrete next information source worth testing, or whether
CT-113 should pause instead of continuing threshold mining.

## Current Assets

Already tested or available locally:

| Information set | Local status | Decision |
| --- | --- | --- |
| OHLCV, taker-flow klines, multi-timeframe indicators | CT-121 through CT-127 exhausted the useful nearby branches | do not tune more nearby thresholds |
| Funding-rate crowding | strongest historical branch in CT-128/CT-130, later weakened by older-holdout and forward evidence | observation only, not a working model |
| Binance Data Vision futures metrics | imported in CT-178 and tested in CT-179/180/200/201 | useful, but no promoted model after broad validation |
| Forward order-book, liquidation, crowding collectors | implemented for forward evidence and droplet monitoring | not enough closed forward-paper evidence |
| Hyperliquid whale tracking | feasible as forward watchlist only | not usable for historical validation now |
| True spot drawdown/rotation | CT-194 through CT-203 tested the public-data family | no paper candidate |

The current conclusion is not "no idea can ever work." It is narrower: the current public candle,
funding, futures metrics, and strict/controlled spot-exit families do not support a working model
under the user's return target and risk constraints.

## Data Source Inventory

| Source | Data type | Historical status | CT-113 suitability |
| --- | --- | --- | --- |
| Binance funding history | point-in-time funding rates | available and already imported | already tested; no fresh edge by itself |
| Binance Data Vision `daily/metrics` | 5m OI, long/short, taker ratio rows | available and already imported | already tested in the latest external OI branches |
| Binance REST order book | current depth snapshot | current only | not usable for old backtests |
| Binance websocket depth/liquidation streams | forward-only order-flow events | can collect from now onward | useful for future evidence, not old holdouts |
| Binance Data Vision `daily/bookDepth` | historical depth by percentage band | available in spot checks | best free/public next validation target |
| CoinGlass, Tardis, CandleFeed, Kaiko, similar vendors | liquidation, depth, heatmap, derivatives risk data | likely paid or trial-based | useful only after a sample/license is acquired |
| Coinalyze | OI/liquidation/long-short history | intraday retention limits in docs | may help, but likely not enough for full old holdouts |
| Hyperliquid wallet tracking | wallet fills/positions | recent/forward constrained | not enough for robust historical validation |

## Binance BookDepth Check

Binance Data Vision `bookDepth` is the only free/public source found that changes the information
set enough to justify one more CT-113 data branch.

Spot checks run on `2026-05-31`:

| URL | Result | Size |
| --- | --- | ---: |
| `data/futures/um/daily/bookDepth/BTCUSDT/BTCUSDT-bookDepth-2025-02-15.zip` | HTTP `200` | `460,635` bytes |
| `data/futures/um/daily/bookDepth/SOLUSDT/SOLUSDT-bookDepth-2025-02-15.zip` | HTTP `200` | `410,588` bytes |
| `data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2025-02-15.zip` | HTTP `200` | `10,945` bytes |

Downloaded BTC sample:

- rows: `28,800`;
- unique timestamps: `2,880`;
- first timestamp: `2025-02-15 00:00:01`;
- last timestamp: `2025-02-15 23:59:32`;
- percentage bands: `-5`, `-4`, `-3`, `-2`, `-1`, `1`, `2`, `3`, `4`, `5`;
- rows per timestamp: `10`;
- columns:

```text
timestamp,percentage,depth,notional
```

Example rows:

```text
2025-02-15 00:00:01,-5,6356.04900000,604784490.50330000
2025-02-15 00:00:01,-4,5436.67300000,519173725.49190000
2025-02-15 00:00:01,-3,4116.55100000,395003094.76800000
2025-02-15 00:00:01,-2,2728.70300000,263127702.83640000
2025-02-15 00:00:01,-1,1246.31100000,120924626.16480000
2025-02-15 00:00:01,1,1456.99600000,142534614.06180000
```

This is not level-2 tick history and it will not identify specific spoofed walls. It is still
materially different from OHLCV because it provides historical visible depth imbalance near the
market. It can support features such as:

- bid depth notional at 1 percent and 2 percent below price;
- ask depth notional at 1 percent and 2 percent above price;
- bid/ask depth imbalance;
- 1h/4h depth z-scores;
- depth compression/expansion before breakouts;
- depth asymmetry combined with funding, OI, and taker pressure.

Point-in-time rule:

- parse `timestamp` as UTC;
- for a decision at `T`, use only book-depth rows with `timestamp <= T`;
- forward-fill with a bounded tolerance, initially `5` minutes;
- do not use future depth buckets or daily aggregates that include future rows.

## Decision

Do not run another model matrix on the existing feature set.

Create the next issue as a data-access spike for Binance Data Vision `bookDepth`:

1. verify coverage for the CT-113 symbols and old holdout windows;
2. estimate storage/runtime cost for 11 to 17 symbols across H2 2024, H1 2025, and Jul-Nov 2025;
3. import a small point-in-time sample;
4. build depth imbalance features;
5. run only a smoke/diagnostic join first;
6. proceed to a strategy matrix only if coverage and join quality pass.

If `bookDepth` is missing, too coarse, too expensive to process, or not predictive in diagnostics,
the next decision should be explicit pause/re-scope of CT-113 until a paid historical
microstructure/liquidation dataset is acquired.

## Next Issue

Created follow-up: `CT-205` - validate Binance Data Vision book-depth archive for CT-113
microstructure features.

Acceptance criteria:

- coverage report for selected symbols and historical windows;
- one reproducible import command and manifest;
- point-in-time feature join with leakage checks;
- selected-position diagnostic against the strongest rejected families;
- clear decision: continue to full matrix, switch to paid vendor acquisition, or pause CT-113.

## Safety

No live trading, paper runtime, order placement, leverage, margin, stop-loss, take-profit, exchange
API, or account state behavior was changed.

Backtests and diagnostics remain research evidence only.

CT-113 stays open.

## References

- Binance public data repository: <https://github.com/binance/binance-public-data>
- Binance Data Vision portal: <https://data.binance.vision/>
- CT-131 order-book/OI/liquidation feasibility:
  `docs/experiments/ct131-orderbook-oi-liquidation-feasibility.md`
- CT-177 external crowding archive research:
  `docs/experiments/ct177-external-crowding-archive-research.md`
- CT-201 broad external OI validation:
  `docs/experiments/ct201-broad-external-oi-validation.md`
- CT-203 controlled-loss spot efficiency:
  `docs/experiments/ct203-controlled-loss-spot-efficiency.md`
