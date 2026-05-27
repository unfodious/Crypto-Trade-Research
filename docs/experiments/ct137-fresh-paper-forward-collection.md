# CT-137 Fresh-Data Forward Paper Collection

Date: 2026-05-27

Issue: CT-137

Epic: CT-113

## Decision

Fresh-data forward paper collection is runnable for the CT-132 negative-funding candidate. The
first public Binance USD-M futures run completed, but it produced no paper trade because the latest
decision timestamp had no candidate passing the CT-132 filters.

This is forward paper infrastructure only. It does not approve live trading, does not prove a
working model, and does not close CT-113.

## What Changed

Added:

- `crypto_trade_research.paper_forward`
- console script: `crypto-trade-run-forward-paper`
- config: `configs/ct137-forward-paper-run.json`

Updated:

- `crypto_trade_research.paper_collector` now carries `entry_price`, `stop_price`, and
  `target_price` into paper signals and ledger entries;
- paper collector filters fail closed when a required feature is missing;
- `crypto_trade_research.paper_monitoring` counts closed paper trades for gate metrics and reports
  open ledger entries separately.

The fresh runner:

- fetches recent public Binance futures `1m` klines;
- fetches recent public Binance futures funding-rate rows;
- generates the same CT-130/CT-132 point-in-time feature set;
- scores the latest closed timestamp through the CT-132 pack;
- writes the current run `signals.json` and `ledger.json`;
- appends de-duplicated cumulative `forward_signals.json` and `forward_ledger.json`;
- resolves previously open paper trades when stop, target, or 12-bar timeout is observable;
- runs CT-135 monitoring against the cumulative ledger.

It does not use API keys and never places, cancels, or mutates live orders.

## Repro Command

Build or refresh the CT-132 pack manifest first:

```sh
python -m crypto_trade_research.paper_trading \
  --config configs/ct132-negative-funding-paper-pack.json
```

Run the fresh-data forward collector:

```sh
python -m crypto_trade_research.paper_forward \
  --config configs/ct137-forward-paper-run.json
```

Generated files:

- `data/generated/ct137_negative_funding_forward_paper/features.parquet`
- `data/generated/ct137_negative_funding_forward_paper/signals.json`
- `data/generated/ct137_negative_funding_forward_paper/ledger.json`
- `data/generated/ct137_negative_funding_forward_paper/forward_signals.json`
- `data/generated/ct137_negative_funding_forward_paper/forward_ledger.json`
- `data/generated/ct137_negative_funding_forward_paper/monitoring_report.json`
- `data/generated/ct137_negative_funding_forward_paper/forward_run.json`

Generated outputs are not committed.

## Fresh Verification Run

The fresh verification run used public Binance USD-M futures data.

| Field | Value |
| --- | ---: |
| run name | `ct137_negative_funding_forward_paper` |
| decision time | `2026-05-27T06:02:00Z` |
| source window start | `2026-05-26T23:01:00Z` |
| source window end | `2026-05-27T06:01:00Z` |
| symbols | `11` |
| candle rows | `4,631` |
| funding rows | `300` |
| latest feature rows | `11` |
| candidate count | `0` |
| signal count | `0` |
| paper takes | `0` |
| cumulative trades | `0` |
| open trades | `0` |
| closed trades | `0` |
| monitoring status | `gate_failed` |
| live order authority | `false` |

Interpretation: the fresh-data path works, but the market snapshot did not meet the negative-funding
candidate filters. That is a no-trade state, not a model pass or reject.

## Schedule

Created an active hourly Codex app automation:

- id: `ct-137-fresh-paper-forward-collection`;
- cadence: hourly;
- workspace: `/Users/unfodious/Projects/crypto-trade-research`;
- scope: rebuild the CT-132 pack if needed, run the CT-137 fresh forward collector, and summarize
  the cumulative ledger and monitoring report.

The automation prompt explicitly forbids live orders, leverage/margin changes, runtime trade-state
writes, and live-trading approval.

## Gate Status

The forward gate fails, as expected:

- `0` closed forward paper trades versus `>=100` required;
- `0` calendar days versus `>=30` required;
- no positive average R evidence yet;
- no symbol/session breadth evidence yet.

The drawdown gate is trivially within limit because there are no closed paper outcomes yet.

## Safety Boundary

This issue remains research-only:

- no live trading approval;
- no order placement;
- no leverage or margin changes;
- no runtime trade-state writes;
- no secret-bearing API calls.

## Next Step

Keep the scheduled collector running until it accumulates enough closed paper outcomes to make a
real decision. CT-113 remains open until a candidate reaches the paper gate or the research path is
explicitly paused or re-scoped.
