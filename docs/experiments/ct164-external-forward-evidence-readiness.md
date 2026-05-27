# CT-164 External Forward Evidence Readiness

Date: 2026-05-27

Issue: CT-164

Epic: CT-113

Status: readiness report, not a trading model

## Objective

Prevent premature validation claims after adding CT-151/153 crowding, CT-158 order-book, CT-160
liquidation, and CT-162 external forward feature streams.

The report answers one narrow question: do we have enough forward evidence to run an external-feature
validation matrix without fooling ourselves?

## Command

```sh
scripts/run_ct164_evidence_readiness_once.sh
```

Equivalent installed entrypoint:

```sh
crypto-trade-build-evidence-readiness --config configs/ct164-evidence-readiness.json
```

## Inputs

- `data/generated/ct162_external_forward_features/external_forward_features_run.json`
- CT-145/CT-146 forward paper run and monitoring artifacts
- CT-156/CT-157 shadow forward paper run and monitoring artifacts

## Gates

Initial gates:

- external feature rows `>=500`;
- crowding snapshots `>=1`;
- order-book snapshots `>=1`;
- liquidation snapshots `>=1`;
- cumulative forward paper signals `>=30`;
- closed forward paper trades `>=30`;
- calendar days `>=7`;
- no working-model claim;
- no live-trading approval.

These gates are intentionally below the final paper-trading promotion gate. They only decide whether
an external-feature validation matrix is worth running. Promotion still requires much stricter
evidence.

## Output

- JSON: `data/generated/ct164_external_forward_evidence_readiness/readiness_report.json`
- Markdown: `data/generated/ct164_external_forward_evidence_readiness/readiness_report.md`

## Decision Rules

- `ready_for_validation`: enough feature rows and enough forward-paper exposure to run the next
  validation matrix.
- `not_ready`: keep collecting forward data and do not interpret external features as edge evidence
  yet.

This report never approves live trading and never marks a working model.

## Initial Smoke Result

Local smoke on 2026-05-27:

- readiness: `not_ready`
- external feature rows: 44
- crowding/order-book/liquidation snapshots: 2 / 1 / 1
- cumulative forward signals: 0
- closed forward trades: 0
- calendar days: 0
- live trading approved: false

Droplet smoke on 2026-05-27:

- readiness: `not_ready`
- external feature rows: 572
- crowding/order-book/liquidation snapshots: 42 / 7 / 3
- cumulative forward signals: 0
- closed forward trades: 0
- calendar days: 0
- live trading approved: false

Interpretation: the external feature pipeline is now populated enough for the feature-data gate, but
the forward-paper exposure gate is still blocked. Do not run an external-feature validation matrix
until CT-145/CT-156 produce enough forward signals/trades and days.

## Monitoring

CT-165 adds droplet monitoring for this readiness gate:

- service: `ct164-evidence-readiness.service`
- timer: `ct164-evidence-readiness.timer`
- unified health stream: `ct164_evidence_readiness`

Expected current health status is operationally healthy but research-not-ready:

- readiness: `not_ready`
- external feature rows: `>=500` on the droplet
- cumulative forward signals/trades/days: still below gate
- working model: false
- live trading approved: false
