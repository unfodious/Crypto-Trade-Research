# CT-184 Adaptive Sizing Shadow Paper Pack

Status: shadow paper pack prepared; no live approval.

CT-183 found two adaptive sizing candidates that passed the historical sizing gates. CT-184 prepares
the safer forward-paper path, not live trading.

## Selected Candidate

Primary shadow candidate:

- `ct184_daily_cap_10_core4_drawdown_throttle`
- symbols: `ADAUSDT`, `AVAXUSDT`, `SOLUSDT`, `SUIUSDT`
- entry family: CT-180 OI/Europe abstention on top of the CT-144/CT-145 expected-R model
- paper sizing:
  - start at `0.25%` risk per accepted paper trade;
  - accept at most `10` paper takes per UTC day;
  - cut risk to `0.10%` when current realized paper drawdown reaches `4%`;
  - cut risk to `0.025%` when current realized paper drawdown reaches `6%`;
  - pause new paper takes when current realized paper drawdown reaches `7.5%`.

CT-183 historical replay evidence for this selected candidate:

| Field | Value |
| --- | ---: |
| Starting equity | `$1,000.00` |
| Final equity | `$1,354.35` |
| Return | `35.44%` |
| Max DD | `6.10%` |
| Accepted trades | `1,288` |
| Skipped trades | `1,248` |

Window reset checks:

| Window | Return | Max DD | Accepted | Skipped | Avg R |
| --- | ---: | ---: | ---: | ---: | ---: |
| `2024H2` | `15.42%` | `3.76%` | `384` | `259` | `0.1523` |
| `2025H1` | `11.64%` | `6.10%` | `678` | `572` | `0.1093` |
| `2025JulNov` | `5.10%` | `3.51%` | `226` | `417` | `0.0920` |

The higher-return alternative remains `daily_cap_10_core3_fixed_0_25pct`, which returned `42.10%`
with `6.82%` max DD historically. CT-184 selects the core-4 throttle variant because it has more
forward sample opportunity and more drawdown buffer.

## Implementation

Added pack and runner configs:

- `configs/ct184-adaptive-sizing-shadow-paper-pack.json`
- `configs/ct184-adaptive-sizing-forward-paper-run.json`

Added runner:

- `scripts/run_ct184_forward_paper_once.sh`

Updated research-only forward paper execution:

- enforces `strategy.paper_sizing.max_signals_per_utc_day` against the persisted
  `forward_ledger.json`;
- records `paper_risk_per_trade_pct` on each paper ledger entry;
- records sizing policy metadata in signal payloads and `forward_run.json`;
- blocks otherwise valid paper takes when the daily paper cap is already reached;
- keeps `live_order_authority=false`.

Updated monitoring:

- computes simulated paper drawdown from each trade's `paper_risk_per_trade_pct` when source metrics
  do not provide drawdown;
- falls back to legacy `1%` only for old ledgers without sizing metadata.

Updated stream health:

- adds `ct184_adaptive_sizing_shadow_forward_paper`;
- expected systemd units are `ct184-forward-paper.service` and `ct184-forward-paper.timer`.

## Local Fresh Tick

Commands:

```sh
.venv/bin/python -m crypto_trade_research.paper_trading \
  --config configs/ct184-adaptive-sizing-shadow-paper-pack.json

.venv/bin/python -m crypto_trade_research.paper_forward \
  --config configs/ct184-adaptive-sizing-forward-paper-run.json
```

Result:

| Field | Value |
| --- | ---: |
| decision time | `2026-05-30T08:51:00Z` |
| candle rows | `4,631` |
| funding rows | `300` |
| futures metrics rows | `407` |
| latest feature rows | `11` |
| candidate count | `0` |
| signal count | `0` |
| paper takes | `0` |
| cumulative trades | `0` |
| open trades | `0` |
| closed trades | `0` |
| paper sizing enabled | `true` |
| paper sizing policy | `daily_cap_10_core4_drawdown_throttle` |
| monitoring status | `gate_failed` |

This is a valid no-trade fresh tick. It only means the current public snapshot did not pass the
entry filters.

Generated artifacts:

- `data/generated/ct184_adaptive_sizing_shadow_paper_pack/pack_manifest.json`
- `data/generated/ct184_adaptive_sizing_shadow_forward_paper/forward_run.json`
- `data/generated/ct184_adaptive_sizing_shadow_forward_paper/monitoring_report.json`

Generated artifacts are not committed.

## Droplet Plan

Run CT-184 as a separate hourly shadow timer, not as a replacement for CT-145, CT-156, or CT-180.

Suggested units:

- service: `ct184-forward-paper.service`
- timer: `ct184-forward-paper.timer`
- command: `/opt/crypto-trade-research/scripts/run_ct184_forward_paper_once.sh`
- suggested offset: minute `36` with randomized delay, to avoid simultaneous Binance public REST
  bursts with the existing timers.

The droplet needs only public Binance REST access. No Binance account keys are required.

## Gate

Before any working-model or live discussion:

- run at least `30` calendar days;
- collect at least `100` closed paper trades;
- average R after costs must stay positive;
- max simulated paper drawdown must stay under `8%`;
- symbol breadth must remain at least `50%` positive;
- session breadth must remain at least `50%` positive;
- no Europe-session trade may be taken;
- no `fm_oi_value_change_1h > 0.015` trade may be taken;
- missing OI metrics for a selected candidate must produce a skip;
- daily paper signal cap must remain enforced;
- every paper ledger entry must include `paper_risk_per_trade_pct`.

## Safety Boundary

No live trading approval.

No working-model claim.

No order placement, cancellation, leverage, margin, runtime sizing, or runtime trade-state writes.

The pack manifest keeps `live_order_authority=false`; the forward runner only writes generated
research artifacts.
