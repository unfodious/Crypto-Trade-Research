# CT-183 CT-180 Adaptive Sizing Throttles

Status: research-only sizing evidence; no live approval.

CT-182 showed that naive fixed-risk sizing makes CT-180 account-level returns meaningful, but
breaches the `8%` drawdown gate. CT-183 tests whether simple throttles can keep the same accepted
trade stream closer to the gate without inventing new entry signals.

## Method

Input replay reports:

- `data/generated/ct180_2024h2_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025h1_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025julnov_oi_high_or_europe_replay/replay_report.json`

CT-183 uses stricter realized-exit accounting than CT-182:

```text
pnl = equity_at_decision * risk_per_trade_pct * net_r
```

The PnL is added only at `exit_time`. This prevents drawdown throttles from reacting to trades that
were not closed yet.

Config and generated report:

- `configs/ct183-ct180-adaptive-sizing-throttles.json`
- `data/generated/ct183_ct180_adaptive_sizing_throttles/report.json`
- `data/generated/ct183_ct180_adaptive_sizing_throttles/report.md`

## Aggregate Results

| Scenario | Final equity | Return | Max DD | Accepted | Skipped | Gate notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `fixed_0_25pct_realized` | `$1,487.74` | `48.77%` | `16.09%` | `2536` | `0` | fails DD/window |
| `fixed_0_10pct_realized` | `$1,179.76` | `17.98%` | `6.69%` | `2536` | `0` | passes, but low growth |
| `drawdown_throttle_4_6_7p5` | `$1,351.33` | `35.13%` | `7.15%` | `2536` | `0` | fails one reset window |
| `daily_cap_10_fixed_0_25pct` | `$1,363.02` | `36.30%` | `7.92%` | `1425` | `1111` | fails symbol avg-R breadth |
| `daily_cap_10_drawdown_throttle` | `$1,265.08` | `26.51%` | `6.09%` | `1425` | `1111` | fails symbol avg-R breadth |
| `daily_cap_10_core3_fixed_0_25pct` | `$1,420.98` | `42.10%` | `6.82%` | `916` | `1620` | passes tested gates |
| `daily_cap_10_core4_drawdown_throttle` | `$1,354.35` | `35.44%` | `6.10%` | `1288` | `1248` | passes tested gates |

## Best Candidate

`daily_cap_10_core3_fixed_0_25pct`:

- symbols: `ADAUSDT`, `AVAXUSDT`, `SUIUSDT`;
- accepts only the first `10` eligible signals per UTC day;
- uses fixed `0.25%` risk per accepted trade;
- final equity from `$1,000`: `$1,420.98`;
- total return: `42.10%`;
- max drawdown: `6.82%`;
- accepted trades: `916`;
- worst realized month: `2025-03`, `-1.90%`.

Window reset checks:

| Window | Final equity | Return | Max DD | Accepted | Skipped | Avg R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024H2` | `$1,153.96` | `15.40%` | `3.62%` | `327` | `316` | `0.1783` |
| `2025H1` | `$1,155.40` | `15.54%` | `6.82%` | `446` | `804` | `0.1333` |
| `2025JulNov` | `$1,065.77` | `6.58%` | `4.29%` | `143` | `500` | `0.1840` |

Symbol checks:

| Symbol | Accepted | Avg R | Profit factor |
| --- | ---: | ---: | ---: |
| `ADAUSDT` | `214` | `0.1511` | `1.394` |
| `AVAXUSDT` | `265` | `0.1673` | `1.459` |
| `SUIUSDT` | `437` | `0.1542` | `1.332` |

## Diversified Alternative

`daily_cap_10_core4_drawdown_throttle` keeps `SOLUSDT` and applies drawdown throttling:

- symbols: `ADAUSDT`, `AVAXUSDT`, `SOLUSDT`, `SUIUSDT`;
- accepts only the first `10` eligible signals per UTC day;
- starts at `0.25%` risk, cuts to `0.10%` after `4%` current DD, `0.025%` after `6%`,
  and pauses at `7.5%`;
- final equity from `$1,000`: `$1,354.35`;
- total return: `35.44%`;
- max drawdown: `6.10%`;
- accepted trades: `1288`.

This is lower return than the core-3 fixed candidate, but has broader symbol coverage and more
drawdown buffer.

## Interpretation

The good news: CT-183 found sizing rules that keep historical returns positive, keep max drawdown
under the `8%` gate, pass reset-window checks, and keep symbol average R positive for the selected
symbol sets.

The caution: this is still a counterfactual replay over already selected CT-180 trades. It is enough
to justify a paper-pack sizing update, not enough to approve live trading.

The daily cap is doing real work. It likely removes low-quality signal clusters during crowded
periods. The core-3 allowlist is also doing real work: after applying the daily cap, `ICPUSDT` became
slightly negative by average R and `SOLUSDT` was weaker than `ADAUSDT`, `AVAXUSDT`, and `SUIUSDT`.

## Decision

Prepare a research-only paper/shadow update candidate from CT-183, preferring one of:

- higher-return candidate: `daily_cap_10_core3_fixed_0_25pct`;
- more diversified candidate: `daily_cap_10_core4_drawdown_throttle`.

Do not approve live trading.

Keep CT-113 open until the paper/shadow candidate has forward evidence.
