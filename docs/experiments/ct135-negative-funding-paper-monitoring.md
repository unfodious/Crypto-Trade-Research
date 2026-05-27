# CT-135 Negative-Funding Paper Monitoring

Date: 2026-05-27

Issue: CT-135

Epic: CT-113

## Decision

Monitoring tooling and a replay-seed report were prepared. The forward paper gate is not passed.

This issue does not approve live trading and does not complete CT-113. The CT-132 candidate is now
monitorable, but the evidence generated here is historical replay smoke evidence, not 30-day
forward paper evidence.

## What Changed

Added expected-R scorer serialization to the model artifact. This is required because the CT-130
candidate is selected by expected-R ranking, not by probability alone.

Updated artifact capability:

- model: `ct130_long_negative_funding_h12_base_top3`
- expected-R model: `ridge_expected_r`
- expected-R feature count: `103`
- expected-R threshold: `-0.20`
- regenerated artifact hash: `c64e8bca8cd66a1403941130b42916472633cfaa1ab1fa9c174ccc8988991cdb`

Added paper monitoring report builder:

- `crypto_trade_research.paper_monitoring`
- console script: `crypto-trade-build-paper-monitoring-report`
- config: `configs/ct135-negative-funding-paper-monitoring.json`

## Repro Commands

Regenerate the CT-130 base artifact with expected-R scorer:

```sh
python -m crypto_trade_research.experiments.runner \
  --config configs/ct130-negative-funding-stability-base.json
```

Rebuild the CT-132 paper pack manifest:

```sh
python -m crypto_trade_research.paper_trading \
  --config configs/ct132-negative-funding-paper-pack.json
```

Build the CT-135 monitoring report:

```sh
python -m crypto_trade_research.paper_monitoring \
  --config configs/ct135-negative-funding-paper-monitoring.json
```

Generated report:

- `data/generated/ct135_negative_funding_paper_monitoring/report.json`

Generated output is not committed.

## Replay-Seed Result

The report uses `expected_r_ridge_top3_oos` trades from the CT-130 baseline report as a monitoring
smoke test.

| Metric | Value |
| --- | ---: |
| Evidence type | `historical_replay_seed` |
| Monitoring status | `gate_failed` |
| Trades | `238` |
| Calendar span | `61` days |
| Avg R after costs | `0.2620` |
| Profit factor | `1.4279` |
| Max drawdown | `7.20%` |
| Single-day positive R share | `31.58%` |
| Positive symbol breadth | `63.64%` |
| Positive session breadth | `100.00%` |
| Expected-R model available | `true` |
| Forward paper gate passed | `false` |

Gate failed for the right reason: the evidence is not forward paper evidence.

Warnings:

- report is a historical replay seed, not forward paper evidence;
- replay trades do not include feature freshness fields;
- replay trades do not include funding latency fields.

## Safety Boundary

No live trading behavior changed.

This work only:

- serializes the research expected-R scoring model;
- validates paper/replay ledger metrics;
- emits monitoring reports.

It does not:

- place live orders;
- cancel live orders;
- change leverage or margin;
- write runtime trade state;
- approve a working model.

## Next Step

The next CT-113 step is a forward paper signal/ledger collector that runs the CT-132 pack against
fresh point-in-time data and writes paper signals with:

- feature freshness;
- funding source latency;
- model artifact hash;
- expected-R score;
- probability score;
- top-N decision context;
- paper fill lifecycle once enough future bars are available.

After that collector has at least `30` calendar days and `>=100` paper trades, CT-135-style
monitoring can make a real continue/reject decision.

## Conclusion

CT-135 made the candidate monitorable and removed the expected-R artifact gap. It did not generate
forward paper evidence yet, so CT-113 remains open and the candidate is still not a working model.
