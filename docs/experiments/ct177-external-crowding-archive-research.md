# CT-177 External Futures Crowding Archive Research

Status: complete; feasible source found; no live approval.

CT-176 rejected broader OHLCV-derived ETH/BTC/breadth abstention rules. CT-177 checks whether
CT-113 can move to genuinely external point-in-time futures positioning data for the same historical
windows instead of continuing with nearby OHLCV thresholds.

## Requirement

The next data source must cover these holdout windows and the CT-113 symbol universe:

- H2 2024: `2024-07-01` through `2025-01-01`;
- H1 2025: `2025-01-01` through `2025-07-01`;
- Jul-Nov 2025: `2025-07-01` through `2025-11-25`;
- symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`,
  `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`.

The data must be point-in-time and usable before a 1m/5m/15m decision timestamp.

## Binance REST Limitation

The live Binance USD-M futures REST endpoints are not enough for old holdouts:

- Open interest statistics: `/futures/data/openInterestHist` is limited to the latest 1 month.
- Global long/short account ratio: `/futures/data/globalLongShortAccountRatio` is limited to the
  latest 30 days.
- Top trader position ratio: `/futures/data/topLongShortPositionRatio` is limited to the latest
  30 days.
- Taker buy/sell volume: `/futures/data/takerlongshortRatio` is limited to the latest 30 days.
- Current order book: `/fapi/v1/depth` is a snapshot endpoint, not a historical endpoint.

So REST alone cannot reconstruct H2 2024 or H1 2025.

## Binance Data Vision Findings

Binance Data Vision is the first feasible historical source.

Official public-data documentation says Binance Data Collection provides downloadable public market
data in daily/monthly files, and futures data includes USD-M futures. Direct S3 prefix checks on
`2026-05-27` found:

| Prefix | Finding | CT-113 use |
| --- | --- | --- |
| `data/futures/um/daily/metrics/{symbol}/` | available | primary next source |
| `data/futures/um/daily/bookDepth/{symbol}/` | available | possible later order-book depth source |
| `data/futures/um/monthly/fundingRate/{symbol}/` | available | already partially used via funding imports |
| `data/futures/um/daily/liquidation*` | no USD-M keys found | not feasible from Binance archive now |
| `data/futures/um/monthly/metrics/` | no keys found | daily only |

Sample `BTCUSDT-metrics-2025-02-15.zip` columns:

```text
create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio
```

The rows are 5-minute point-in-time records. Example first timestamp:

```text
2025-02-15 00:05:00,BTCUSDT,...
```

Coverage spot checks returned HTTP `200` for all 11 CT-113 symbols on:

| Date | Coverage |
| --- | --- |
| `2024-07-15` | 11 / 11 symbols |
| `2025-02-15` | 11 / 11 symbols |
| `2025-10-15` | 11 / 11 symbols |

This is enough to attempt a historical import for the three CT-113 validation windows.

## Candidate Feature Contract

Use daily metrics files as a new research dataset, separate from OHLCV and funding:

| Source column | Proposed feature meaning |
| --- | --- |
| `sum_open_interest` | contract open interest |
| `sum_open_interest_value` | notional open interest |
| `count_toptrader_long_short_ratio` | top trader long/short ratio by accounts/count |
| `sum_toptrader_long_short_ratio` | top trader long/short ratio by position/sum |
| `count_long_short_ratio` | global long/short account ratio |
| `sum_taker_long_short_vol_ratio` | taker buy/sell volume ratio |

Derived features should be point-in-time:

- 5m value and lagged value;
- 1h/4h rolling z-score or percentile;
- OI expansion/contraction;
- crowding divergence: top-trader ratio minus global ratio;
- short-squeeze/long-squeeze proxy: OI change plus taker imbalance plus price return;
- relative symbol crowding vs BTC/ETH and market median.

Join rule:

- parse `create_time` as UTC;
- for a decision at `T`, use only metrics with `create_time <= T`;
- forward-fill metrics at a bounded tolerance such as 10 minutes;
- do not use any future metrics bucket.

## Liquidations And Heatmaps

Binance Data Vision does not currently expose a usable USD-M `liquidationSnapshot` archive. The old
public-data issue trail also indicates historical liquidation snapshots have been problematic for
USD-M after `2024-03-31`.

External options:

- CoinGlass V4 advertises futures liquidation history, liquidation heatmap, OI history,
  long/short ratio history, and taker buy/sell volume history.
- Coinalyze exposes open-interest, liquidation, and long/short history endpoints, but its
  documentation says intraday history keeps only 1500-2000 datapoints and old intraday data is
  deleted daily; daily history is retained.
- CandleFeed advertises backtest-grade historical Binance derivatives data back to 2019 and
  aggregated liquidation history from 2019, with tick-level liquidation events from March 2026.
- Kaiko advertises institutional derivatives risk indicators, including contract-level open
  interest and liquidation insights.

These are useful references, but the immediately actionable free/public path is Binance Data Vision
`daily/metrics`.

## Decision

Feasible next data source found: Binance Data Vision USD-M daily metrics.

Do not pursue more OHLCV-derived abstention thresholds until metrics history is imported and tested.

No working model claim.

No paper-to-live promotion.

Keep CT-113 open.

## Next Step

Create and run the next issue to import Binance Data Vision futures metrics for the three CT-113
historical windows, generate point-in-time crowding features, and replay CT-145/CT-156 plus a
metrics-aware abstention/ranking matrix.

References:

- Binance public data repository: <https://github.com/binance/binance-public-data>
- Binance open interest statistics REST docs:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics>
- Binance global long/short REST docs:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio>
- Binance top trader position ratio REST docs:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio>
- Binance taker buy/sell volume REST docs:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume>
- Binance order book REST docs:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book>
- Coinalyze API docs: <https://api.coinalyze.net/v1/doc/>
- CoinGlass V4 OI history docs: <https://docs.coinglass.com/reference/oi-ohlc-histroy>
- CandleFeed docs: <https://candlefeed.ai/docs/>
- Kaiko derivatives risk indicators:
  <https://www.kaiko.com/products/derivatives-risk-indicators>
