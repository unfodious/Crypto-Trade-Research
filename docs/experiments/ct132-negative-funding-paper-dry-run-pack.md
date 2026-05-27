# CT-132 Negative-Funding Paper Dry-Run Pack

Date: 2026-05-27

Issue: CT-132

Epic: CT-113

## Decision

Paper/dry-run pack prepared. No live trading approval.

This task moves the CT-130 candidate from research evidence to a reproducible paper-trading dry-run
pack. It does not mark CT-113 complete because there is no forward paper evidence yet.

Candidate:

- `ct130_long_negative_funding_h12_base_top3`
- long-only Binance USD-M futures research candidate
- ranking: expected-R ridge, top `3` candidates per decision time
- selected expected-R threshold: `-0.20`
- selected probability threshold: `0.55`
- stop: `0.4%`
- target: `0.8%`
- timeout: `12` closed 1m bars

CT-130 research evidence:

| Metric | Value |
| --- | ---: |
| OOS trades | `238` |
| OOS avg R | `0.2620` |
| Rule-only avg R | `-0.6642` |
| OOS max drawdown | `7.20%` |
| OOS profit factor | `1.4279` |
| Stability artifact | `pass` |

## Pack Artifact

Config:

- `configs/ct132-negative-funding-paper-pack.json`

Builder:

- `crypto_trade_research.paper_trading`
- console script: `crypto-trade-build-paper-pack`

Repro command:

```sh
python -m crypto_trade_research.paper_trading \
  --config configs/ct132-negative-funding-paper-pack.json
```

Generated manifest:

- `data/generated/ct132_negative_funding_paper_dry_run_pack/pack_manifest.json`

Dry run result:

- schema: `research.paper-trading-pack.v1`
- status: `paper_dry_run_pack_ready`
- `paper_trading_approved=true`
- `live_trading_approved=false`
- `working_model=false`
- `live_order_authority=false`

The generated manifest is intentionally reproducible generated output and is not committed.

## Strategy Rules

Universe:

- `SOLUSDT`
- `SUIUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `ICPUSDT`
- `ATOMUSDT`
- `XRPUSDT`
- `TONUSDT`
- `DOTUSDT`
- `BTCUSDT`
- `ETHUSDT`

Signal:

- closed `1m` candles only;
- funding rows must have `funding_time` and `source_available_at` at or before the signal timestamp;
- filters:
  - `funding_rate <= -0.00002`;
  - `funding_rate_zscore_20 <= -0.25`;
  - `close_location >= 0.45`;
- score candidates with the CT-130 model artifact;
- rank by expected-R ridge score;
- take top `3` candidates per decision time;
- apply `loss_cooldown_signals = 2`;
- do not exceed `max_trades_per_decision_time = 3`.

Paper exit model:

- stop: `0.4%`;
- target: `0.8%`;
- timeout: `12` closed 1m bars;
- tie breaker: `stop_first`;
- round-trip cost assumption: `0.07%`.

## Safety Boundary

Allowed actions:

- log a signal;
- log a skip;
- create a paper fill in a paper ledger;
- compute paper PnL and R-multiple metrics.

Forbidden actions:

- place a live order;
- cancel a live order;
- change leverage;
- change margin;
- write runtime trade state;
- use live credentials.

This pack must only emit `take` or `skip` style decisions compatible with `ml-inference.v1`. Any
runtime integration remains a separate future issue with trading-safety review.

## Paper Gate

Minimum before any further promotion review:

- at least `30` calendar days;
- at least `100` paper trades;
- average R after estimated costs remains positive;
- max simulated drawdown remains `<= 8%`;
- no single day contributes more than `75%` of positive R;
- positive symbol breadth is at least `50%`;
- positive session breadth is at least `50%`;
- paper signal generation reconciles with CT-130 research rules.

Pause or kill conditions:

- average R is negative after `50` paper trades;
- simulated drawdown exceeds `8%`;
- risk-off slice dominates losses;
- funding data is missing, delayed, or not source-timestamped;
- generated paper signals diverge from research artifact rules.

## Monitoring

Daily review must include:

- paper average R after costs;
- profit factor;
- trade count;
- max drawdown and duration;
- symbol breadth;
- session breadth;
- single-day positive R concentration;
- rejection reason distribution;
- funding source latency;
- feature freshness.

The paper ledger must keep enough detail to reconstruct each signal:

- model id and version;
- artifact hash;
- signal timestamp;
- features timestamp;
- feature freshness;
- source funding timestamp;
- expected R;
- target-before-stop probability;
- action: `take` or `skip`;
- reason codes;
- hard risk blocks;
- paper fill reason;
- net R.

## Reconciliation

Before paper evidence is trusted, a daily reconciliation report must verify:

- feature set version matches the CT-130 model artifact;
- model artifact hash matches the CT-132 pack manifest;
- candle and funding inputs are point-in-time;
- top-N ranking matches the pack rule;
- stop, target, timeout, and cost assumptions match this document;
- rejected candidates have reason codes.

## Conclusion

CT-132 prepares the CT-130 candidate for a fake-executor or paper-ledger dry run. It is the strongest
CT-113 branch so far, but it is not a working model until paper evidence passes the gate. CT-113
must remain open.
