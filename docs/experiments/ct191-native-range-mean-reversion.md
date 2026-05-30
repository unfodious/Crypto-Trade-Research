# CT-191 Native 5m/15m Range Mean-Reversion

Status: rejected; research-only evidence.

CT-191 tested the next branch after CT-189 rejected native 5m/15m long continuation and CT-190
rejected native 5m/15m short risk-off continuation. The goal was to check whether the same noisy
altcoin behavior that hurts continuation can be monetized by faster range/mean-reversion exits.

## Thesis

The range hypothesis was:

- altcoin continuation may be weak because price often snaps back after local extremes;
- shorter 1R mean-reversion exits may harvest that noise better than 3R continuation exits;
- wick reclaim/rejection, low/high range position, RSI extremes, ADX range filters, and risk-on/off
  context may separate better reversals from falling-knife or squeeze conditions.

## Method

The scan reused the native-timeframe process from CT-189 and CT-190:

1. read the three CT-180 historical holdout datasets;
2. aggregate 1m OHLCV into native closed `5m` and `15m` bars;
3. generate point-in-time OHLCV features on native timeframe bars;
4. generate 1R long and short labels:
   - `5m`: stop `0.6%`, target `0.6%`, horizon `6` bars;
   - `15m`: stop `1.0%`, target `1.0%`, horizon `4` bars;
   - cost `0.07%`, `stop_first`;
5. test predeclared range/mean-reversion families on `ADAUSDT`, `AVAXUSDT`, and `SUIUSDT`;
6. cap to the first `10` signals per UTC day.

Windows:

- `2024H2`
- `2025H1`
- `2025JulNov`

Long setups:

- `long_range_low_rsi`: low range position, low Bollinger position, RSI <= 38, ADX <= 28, close not
  at the bar low;
- `long_lower_wick_reclaim`: low range position, large lower wick, close reclaim, ADX <= 30;
- `long_riskon_range_low`: low range position, RSI <= 42, risk-on score >= 0.35, ADX <= 30.

Short setups:

- `short_range_high_rsi`: high range position, high Bollinger position, RSI >= 62, ADX <= 28, close
  not at the bar high;
- `short_upper_wick_reject`: high range position, large upper wick, weak close, ADX <= 30;
- `short_riskoff_range_high`: high range position, RSI >= 58, risk-on score <= 0.65, ADX <= 30.

## Aggregate Results

| Timeframe | Direction | Setup | Trades | Weighted Avg R | Window avg R |
| --- | --- | --- | ---: | ---: | --- |
| `5m` | long | `long_range_low_rsi` | `2795` | `-0.1148` | `-0.1354`, `-0.0899`, `-0.1241` |
| `5m` | long | `long_lower_wick_reclaim` | `5030` | `-0.1551` | `-0.1250`, `-0.1762`, `-0.1668` |
| `5m` | long | `long_riskon_range_low` | `3724` | `-0.1483` | `-0.1564`, `-0.1624`, `-0.1156` |
| `5m` | short | `short_range_high_rsi` | `2649` | `-0.0836` | `-0.1013`, `-0.1208`, `-0.0183` |
| `5m` | short | `short_upper_wick_reject` | `5085` | `-0.0736` | `-0.0744`, `-0.1068`, `-0.0317` |
| `5m` | short | `short_riskoff_range_high` | `3522` | `-0.0866` | `-0.0968`, `-0.1159`, `-0.0403` |
| `15m` | long | `long_range_low_rsi` | `878` | `-0.0507` | `-0.0437`, `-0.0546`, `-0.0540` |
| `15m` | long | `long_lower_wick_reclaim` | `2961` | `-0.0932` | `-0.1129`, `-0.0810`, `-0.0846` |
| `15m` | long | `long_riskon_range_low` | `1563` | `-0.0951` | `-0.1073`, `-0.1226`, `-0.0230` |
| `15m` | short | `short_range_high_rsi` | `789` | `-0.0289` | `-0.0260`, `-0.0067`, `-0.0589` |
| `15m` | short | `short_upper_wick_reject` | `3248` | `-0.0596` | `-0.0924`, `-0.0463`, `-0.0329` |
| `15m` | short | `short_riskoff_range_high` | `1357` | `0.0046` | `-0.0006`, `-0.0402`, `0.0600` |

## Interpretation

Native 5m/15m range mean-reversion does not solve the monthly-return objective. The broad rows are
negative after costs. The only positive aggregate row, `15m short_riskoff_range_high`, is only
`0.0046R` and fails stability: approximately flat in `2024H2`, negative in `2025H1`, and positive
only in `2025JulNov`.

This rejects the remaining simple OHLCV-derived branch tested under CT-191. Across CT-189, CT-190,
and CT-191:

- native long continuation is negative;
- native short/risk-off continuation is negative or unstable;
- native range/mean-reversion is negative or too close to zero;
- the existing CT-180/CT-184 OI/Europe candidate remains the best positive stream, but CT-186 and
  CT-187 showed it is not large enough for a `30%` monthly objective at sane drawdown.

The conclusion is not "add leverage." The conclusion is that entry quality is still too weak. The
next branch needs a genuinely different information source, not another nearby RSI/ADX/timeframe
filter.

## External-Flow Readiness Check

The new paper-trading droplet at `209.38.188.101` is collecting external forward streams. A read-only
SSH inspection on 2026-05-30 showed active timers for:

- Binance crowding/open-interest snapshots;
- Binance order-book snapshots;
- Binance force-liquidation windows;
- external feature table generation;
- CT-145, CT-156, and CT-184 forward-paper streams;
- CT-164 evidence readiness.

Latest observed CT-164 readiness on the droplet:

| Gate | Value | Status |
| --- | ---: | --- |
| external feature rows | `26,587` | pass |
| crowding snapshots | `830` | pass |
| order-book snapshots | `796` | pass |
| liquidation snapshots | `791` | pass |
| cumulative forward signals | `34` | pass |
| closed forward trades | `0` | fail |
| calendar days | `0` | fail |
| working model claim | `false` | pass |
| live trading approval | `false` | pass |

The external feature dataset is now populated enough for feature engineering, but it is not enough
for validation. There are still no closed forward-paper trades and not enough calendar time. CT-184
itself had `0` candidates/signals/trades at the latest inspected decision time, so it also remains a
monitoring stream, not a working model.

## Decision

Reject CT-191 as a native 5m/15m range mean-reversion candidate.

Do not change CT-184 paper trading from this evidence.

Keep CT-113 open.

Open the next hypothesis around external-flow validation, with two tracks:

1. use the already-running droplet streams to build an external-flow diagnostic matrix once closed
   forward labels exist;
2. research/import a historical liquidation/order-book/whale-flow source if the monthly target
   cannot wait for enough forward evidence.

No live trading approval. No working model claim.
