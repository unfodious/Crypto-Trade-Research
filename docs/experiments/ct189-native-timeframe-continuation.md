# CT-189 Native 5m/15m Continuation Scan

Status: rejected; research-only evidence.

CT-188 showed that higher-timeframe filters over the current 1m CT-180 entry stream do not
materially improve average R or runner share. CT-189 tested the next stricter idea: change the entry
and label timeframe itself to native 5m/15m continuation bars.

## Thesis

The trading hypothesis was:

- 1m entries may be too noisy for large monthly-return objectives;
- native 5m/15m bars may capture cleaner directional auctions;
- trend, breakout, pullback, or ADX continuation on 5m/15m may produce more `3R+` runners than
  1m entries filtered by 5m/15m context.

## Method

The scan used existing research primitives without touching live trading:

1. read the three historical holdout datasets used by CT-180;
2. aggregate 1m OHLCV into native closed `5m` and `15m` bars;
3. generate point-in-time OHLCV features on the native timeframe bars;
4. generate long labels:
   - `5m`: stop `0.6%`, target `1.8%`, horizon `12` bars;
   - `15m`: stop `1.0%`, target `3.0%`, horizon `8` bars;
   - cost `0.07%`, `stop_first`;
5. test predeclared continuation families on `ADAUSDT`, `AVAXUSDT`, `SUIUSDT`;
6. cap to the first `10` signals per UTC day.

Windows:

- `2024H2`
- `2025H1`
- `2025JulNov`

## Aggregate Results

| Timeframe | Setup | Trades | Weighted Avg R | Window avg R |
| --- | --- | ---: | ---: | --- |
| `5m` | trend continuation | `5120` | `-0.1427` | `-0.1335`, `-0.1595`, `-0.1335` |
| `5m` | breakout | `5105` | `-0.1135` | `-0.1069`, `-0.1020`, `-0.1362` |
| `5m` | pullback | `5120` | `-0.0866` | `-0.1130`, `-0.1197`, `-0.0128` |
| `5m` | ADX trend | `5120` | `-0.1380` | `-0.0982`, `-0.1710`, `-0.1470` |
| `15m` | trend continuation | `5097` | `-0.0740` | `0.0011`, `-0.1198`, `-0.1121` |
| `15m` | breakout | `3840` | `-0.0948` | `-0.0292`, `-0.1133`, `-0.1530` |
| `15m` | pullback | `4704` | `-0.0800` | `-0.1053`, `-0.0327`, `-0.1079` |
| `15m` | ADX trend | `5015` | `-0.0920` | `-0.0446`, `-0.1345`, `-0.0993` |

## Interpretation

Native long continuation does not solve the monthly-return objective. It is worse than the current
CT-184/CT-183 stream, not merely insufficient. Even the least-bad family, 15m trend continuation, is
approximately flat in `2024H2` and negative in both later windows.

This is consistent with earlier CT-102/CT-110/CT-122 long-breakout failures: broad long continuation
on these alt symbols is structurally weak after costs.

The result does not mean higher timeframes are useless. It means the next useful branch should not
be long continuation. A more plausible market-mechanics hypothesis is native 5m/15m short/risk-off
continuation, where crypto forced selling, liquidation cascades, and beta shocks may create cleaner
directional legs.

## Decision

Reject CT-189 as a native long 5m/15m continuation candidate.

Do not change CT-184 paper trading from this evidence.

Open the next hypothesis around native 5m/15m short/risk-off deleveraging continuation.
