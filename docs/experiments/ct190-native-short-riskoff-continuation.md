# CT-190 Native 5m/15m Short Risk-Off Continuation Scan

Status: rejected; research-only evidence.

CT-190 tested the follow-up market-mechanics hypothesis after CT-189 rejected native long
continuation. In crypto, large fast moves often happen on forced selling, liquidation cascades, and
BTC/ETH beta shocks, so short/risk-off continuation was a plausible next branch.

## Thesis

The short-side hypothesis was:

- risk-off regimes may produce cleaner continuation than long risk-on regimes;
- BTC/ETH weakness and weak market breadth may align altcoin downside;
- breakdowns on 5m/15m bars may capture forced selling better than 1m entries.

## Method

The scan reused the CT-189 native timeframe process:

1. read the three CT-180 historical holdout datasets;
2. aggregate 1m OHLCV into native closed `5m` and `15m` bars;
3. generate point-in-time OHLCV features on native timeframe bars;
4. generate short labels:
   - `5m`: stop `0.6%`, target `1.8%`, horizon `12` bars;
   - `15m`: stop `1.0%`, target `3.0%`, horizon `8` bars;
   - cost `0.07%`, `stop_first`;
5. test predeclared short/risk-off families on `ADAUSDT`, `AVAXUSDT`, `SUIUSDT`;
6. cap to the first `10` signals per UTC day.

Windows:

- `2024H2`
- `2025H1`
- `2025JulNov`

## Aggregate Results

| Timeframe | Setup | Trades | Weighted Avg R | Window avg R |
| --- | --- | ---: | ---: | --- |
| `5m` | risk-off trend | `5120` | `-0.1712` | `-0.1671`, `-0.1255`, `-0.2327` |
| `5m` | breakdown | `5119` | `-0.1308` | `-0.1341`, `-0.1480`, `-0.1054` |
| `5m` | pullback short | `5120` | `-0.1123` | `-0.0602`, `-0.0926`, `-0.2019` |
| `5m` | ADX risk-off | `5120` | `-0.1696` | `-0.1484`, `-0.1427`, `-0.2295` |
| `5m` | BTC/ETH weak | `5120` | `-0.1501` | `-0.1807`, `-0.0695`, `-0.2110` |
| `15m` | risk-off trend | `5092` | `-0.0733` | `-0.0338`, `-0.1038`, `-0.0851` |
| `15m` | breakdown | `3792` | `-0.0299` | `-0.0010`, `-0.1006`, `0.0210` |
| `15m` | pullback short | `4873` | `-0.0849` | `-0.1239`, `-0.0540`, `-0.0729` |
| `15m` | ADX risk-off | `4990` | `-0.0542` | `-0.0298`, `-0.0648`, `-0.0714` |
| `15m` | BTC/ETH weak | `5084` | `-0.1035` | `-0.1103`, `-0.0936`, `-0.1072` |

## Interpretation

Native 5m/15m short continuation is not a solution either. The least-bad row, `15m breakdown`,
was only slightly positive in `2025JulNov`, roughly flat in `2024H2`, and clearly negative in
`2025H1`. That is not stable enough for a paper candidate or a monthly-return target.

The broader lesson from CT-189 and CT-190 is that simple directional continuation on these altcoins,
long or short, is structurally weak after costs under the tested rules. The search should shift away
from directional continuation families and toward either:

- range/mean-reversion structures with quicker profit capture, or
- external point-in-time information that is not contained in OHLCV/funding alone, such as order book
  imbalance, liquidation clusters, or whale/order-flow forward evidence.

## Decision

Reject CT-190 as a native 5m/15m short/risk-off continuation candidate.

Do not change CT-184 paper trading from this evidence.

Keep CT-113 open.
