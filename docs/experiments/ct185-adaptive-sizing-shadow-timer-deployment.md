# CT-185 Adaptive Sizing Shadow Timer Deployment

Status: CT-184 shadow paper timer deployed on `Paper-trading-test`; no live approval.

CT-185 deploys the CT-184 adaptive sizing shadow forward-paper runner to the paper-trading droplet.
This is research-only. It does not place, cancel, resize, or authorize live orders.

## Target

- droplet: `Paper-trading-test`
- host: `209.38.188.101`
- path: `/opt/crypto-trade-research`
- service: `ct184-forward-paper.service`
- timer: `ct184-forward-paper.timer`
- command: `/opt/crypto-trade-research/scripts/run_ct184_forward_paper_once.sh`
- schedule: hourly at minute `36`, with `30s` randomized delay

Existing timers were left unchanged:

- `ct145-forward-paper.timer`: hourly
- `ct156-forward-paper.timer`: minute `12`

`ct180-forward-paper.timer` was not installed on this droplet at deployment time; CT-185 did not
change that state.

## Deployed Files

The droplet copy is not a git checkout, so CT-185 copied only the required research files and
source artifacts:

- `configs/ct184-adaptive-sizing-shadow-paper-pack.json`
- `configs/ct184-adaptive-sizing-forward-paper-run.json`
- `scripts/run_ct184_forward_paper_once.sh`
- `src/crypto_trade_research/paper_forward.py`
- `src/crypto_trade_research/paper_monitoring.py`
- `src/crypto_trade_research/research_stream_health.py`
- `data/generated/ct144_no_ton_detailed/baseline_report.json`
- `data/generated/ct144_no_ton_detailed/stability_report.json`

The CT-144 model artifact was already present on the droplet.

## Smoke Evidence

Manual remote smoke before systemd:

```sh
cd /opt/crypto-trade-research
.venv/bin/python -m crypto_trade_research.paper_trading \
  --config configs/ct184-adaptive-sizing-shadow-paper-pack.json
.venv/bin/python -m crypto_trade_research.paper_forward \
  --config configs/ct184-adaptive-sizing-forward-paper-run.json
```

Systemd-managed smoke:

```sh
systemctl start ct184-forward-paper.service
systemctl show ct184-forward-paper.service -p Result -p ExecMainStatus -p ActiveState
systemctl show ct184-forward-paper.timer -p ActiveState -p NextElapseUSecRealtime
```

Result:

| Field | Value |
| --- | --- |
| service result | `success` |
| exec status | `0` |
| service state | `inactive/dead` after oneshot success |
| timer state | `active/waiting` |
| next timer run | `2026-05-30T10:36:04Z` |
| decision time | `2026-05-30T09:54:00Z` |
| candle rows | `4,631` |
| funding rows | `300` |
| futures metrics rows | `396` |
| latest feature rows | `11` |
| candidates / signals / takes | `0 / 0 / 0` |
| cumulative trades | `0` |
| paper sizing enabled | `true` |
| paper sizing policy | `daily_cap_10_core4_drawdown_throttle` |
| monitoring status | `gate_failed` |

`gate_failed` is expected at deployment start because the forward gate requires at least `30`
calendar days and `100` closed paper trades.

## Health Summary

`crypto_trade_research.research_stream_health` includes
`ct184_adaptive_sizing_shadow_forward_paper`.

CT-184 stream status:

- service: `Result=success`, `ExecMainStatus=0`
- timer: `active/waiting`
- health warnings: none
- source warnings: none
- live trading approved: `false`
- working model: `false`

The aggregate health report still returned `overall_status=warning` because `ct180` forward-paper
artifacts and timer are absent on this droplet. That was pre-existing and outside CT-185 scope.

## Safety Boundary

No live trading approval.

No working-model claim.

No Binance credentials are required for CT-184; it uses public REST data only.

No live order placement, cancellation, leverage, margin, runtime sizing, or runtime trade-state code
was changed.
