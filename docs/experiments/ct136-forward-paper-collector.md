# CT-136 Forward Paper Signal And Ledger Collector

Date: 2026-05-27

Issue: CT-136

Epic: CT-113

## Decision

Research-only paper signal/ledger collector prepared. No live trading approval.

The collector can generate `ml-inference.v1`-style paper signals for the CT-132 pack, rank
candidates with the serialized CT-130 expected-R model, and write a paper ledger. The dry run uses
historical CT-130 feature/label artifacts to prove the contract and ledger shape. It is not forward
paper evidence yet.

## Implementation

Added:

- `crypto_trade_research.paper_collector`
- console script: `crypto-trade-run-paper-collector`
- config: `configs/ct136-negative-funding-paper-collector.json`
- monitoring config: `configs/ct136-negative-funding-paper-collector-monitoring.json`

The collector:

- reads the CT-132 pack manifest;
- loads the CT-130 model artifact;
- requires `expected_r_model` to be present;
- applies CT-132 candidate filters;
- scores candidates with probability and expected-R;
- ranks candidates by expected-R;
- takes top `3` when expected-R is above the selected threshold;
- writes signal JSON and paper ledger JSON;
- optionally resolves historical fills from labels for dry-run validation.

It never places orders, changes leverage, changes margin, or writes runtime trade state.

## Repro Commands

Build the CT-132 pack manifest first:

```sh
python -m crypto_trade_research.paper_trading \
  --config configs/ct132-negative-funding-paper-pack.json
```

Run the collector dry run:

```sh
python -m crypto_trade_research.paper_collector \
  --config configs/ct136-negative-funding-paper-collector.json
```

Run monitoring on the collector ledger:

```sh
python -m crypto_trade_research.paper_monitoring \
  --config configs/ct136-negative-funding-paper-collector-monitoring.json
```

Generated files:

- `data/generated/ct136_negative_funding_paper_collector/signals.json`
- `data/generated/ct136_negative_funding_paper_collector/ledger.json`
- `data/generated/ct136_negative_funding_paper_collector/monitoring_report.json`

Generated files are not committed.

## Dry-Run Result

The dry run selected the latest available historical decision time with a paper take.

| Field | Value |
| --- | --- |
| mode | `historical_dry_run` |
| decision time | `2026-05-24T23:32:00Z` |
| candidate count | `1` |
| signal count | `1` |
| take count | `1` |
| ledger entries | `1` |
| symbol | `TONUSDT` |
| expected R | `-0.1245` |
| threshold | `-0.20` |
| rank | `1` of top `3` |
| probability | `0.5867` |
| feature freshness | `0s` |
| funding source latency | `12719.998s` |
| paper status | `closed` |
| historical net R | `-0.0193` |
| live order authority | `false` |

Monitoring correctly fails the paper gate because this is only one historical dry-run trade, not
30 days and 100 forward paper trades.

## Signal Contract

Each signal includes:

- `contract_version = ml-inference.v1`;
- model id and version;
- artifact hash;
- symbol and timeframe;
- signal timestamp;
- features timestamp;
- feature freshness seconds;
- funding source latency seconds;
- expected-R score;
- target-before-stop probability;
- rank and top-N;
- `take` or `skip`;
- reason codes;
- hard risk blocks.

## Ledger Contract

Paper ledger entries include:

- decision time;
- symbol and timeframe;
- side;
- model id, version, and artifact hash;
- expected-R score;
- probability;
- rank;
- feature freshness;
- funding source latency;
- paper status;
- net R when a dry-run label or future paper fill resolves the trade.

## Remaining Gap

This collector currently proves the paper signal/ledger contract using existing artifacts. A true
forward paper run still needs a scheduled fresh-data source that appends new point-in-time features
and later resolves open paper entries after stop, target, or 12-bar timeout.

CT-113 must remain open until forward paper evidence reaches:

- at least `30` calendar days;
- at least `100` paper trades;
- positive average R after costs;
- max simulated drawdown `<= 8%`;
- acceptable symbol/session breadth;
- no source-timestamp or reconciliation failures.

## Conclusion

CT-136 makes the CT-132 candidate runnable as a research-only paper signal/ledger process. It does
not approve live trading and does not prove the model works forward yet.
