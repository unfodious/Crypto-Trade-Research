# CT-154 Droplet Research Stream Health Summary

Date: 2026-05-27

Issue: CT-154

Epic: CT-113

## Decision

Added a unified research-only health summary command for the active CT-113 droplet streams:

- CT-145 / CT-146 no-TON forward paper;
- CT-156 / CT-157 high-beta+DOT shadow forward paper;
- CT-149 / CT-150 Hyperliquid whale watchlist;
- CT-151 / CT-152 / CT-153 Binance crowding snapshots.

The command reads existing generated JSON artifacts and, when available, systemd unit state. It does
not submit orders, modify collectors, change leverage, change stops, or write runtime trading state.

## Command

From `/opt/crypto-trade-research` on the droplet:

```sh
scripts/run_ct154_research_stream_health.sh
```

For local artifact-only checks:

```sh
crypto-trade-research-stream-health --root . --skip-systemd
```

## Output

The report schema is `research.droplet_stream_health.v1`.

Top-level fields:

- `overall_status`: `ok` unless there is an infrastructure or artifact health warning;
- `warnings`: missing files, failed systemd units, or unexpected CT-153 row counts;
- `source_warnings`: market/source messages that should be visible but do not automatically mean
  the collector is unhealthy, such as a watched wallet having no open positions.

Important stream fields:

- CT-145: latest decision time, candidate/signal/take counts, trade counts, monitoring gate status,
  average R, drawdown, and exit telemetry counters;
- CT-156: the same forward-paper fields for the high-beta+DOT shadow stream;
- CT-149: latest snapshot time, position count, fill count, alert count, and wallet warnings;
- CT-151/153: latest generated time, generator version, period, symbol count, row count, and source
  warnings.

## Manual Smoke Result

Local artifact-only run after CT-153:

| Field | Value |
| --- | ---: |
| overall status | `ok` |
| health warnings | `0` |
| source warnings | `1` |
| CT-145 trade count | `0` |
| CT-149 position count | `0` |
| CT-151/153 row count | `55` |

The one source warning is expected while the watched Hyperliquid wallet has no open perp position.

## Use In Monitoring

Use this command in CT-146, CT-150, and CT-152 checks before deeper inspection. The command is only a
health/evidence summarizer; CT-113 still requires separate forward paper evidence before any working
model claim.
