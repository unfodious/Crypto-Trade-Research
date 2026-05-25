# Post CT-34 ML Research Audit

Date: 2026-05-25
Scope: `crypto-trade-research` after YouTrack epic `CT-34`.

## Summary

The CT-34 pipeline is complete enough for fake-fixture research runs: dataset ingestion, feature
generation, labels, walk-forward evaluation, baseline comparison, meta-strategy filtering, model
registry, inference contract, safety gates, framework feasibility, and an end-to-end runbook.

The next useful work is not a larger model. The next useful work is parity and safety hardening so
future experiments cannot overstate out-of-sample performance.

## Findings

### Major: Baseline reports mix training rows into headline strategy reports

`train_and_evaluate_baselines` trains on the train split, then reports `rule_only` and
`linear_probability` over train + validation + test rows. It also computes a separate
`linear_probability_oos` report for the decision, but that report is not exposed as a first-class
strategy in the generated JSON/Markdown.

Risk: a fresh agent may compare headline strategy metrics and mistake in-sample performance for
out-of-sample evidence.

Expected fix: make OOS-only reports first-class, label train/validation/test metrics explicitly, and
make generated Markdown lead with validation/test evidence.

### Major: Same-bar target/stop ambiguity is optimistic

Trade labels use OHLC future bars. When a target and stop both occur in the same future candle, the
current tie rule treats target as first because `time_to_target <= time_to_stop` returns true.

Risk: OHLC data does not contain intrabar path order. The current default can overstate
target-before-stop labels and inflate expected R.

Expected fix: add configurable tie handling with a pessimistic default, such as `stop_first`,
`target_first`, `skip_ambiguous`, or `separate_ambiguous_label`, and test long/short cases.

### Major: Backtest and meta-strategy exposure are event-only, not duration-aware

`evaluate_signal_strategy` treats each signal as an immediate realized R event. Exposure is `1.0` if
there is any trade, and meta-strategy symbol exposure only accumulates accepted risk without an exit
or duration model.

Risk: portfolio-level drawdown, concurrent exposure, turnover, and symbol/BTC-beta caps cannot be
trusted for strategies with overlapping holding periods.

Expected fix: introduce entry/exit timestamps or holding-period assumptions, compute concurrent
exposure, and make meta-strategy exposure caps duration-aware before paper-trading parity work.

### Normal: Inference response freshness is not cross-checked

`validate_inference_response` validates timestamp formats and non-negative `data_freshness_seconds`,
but it does not verify that freshness equals `signal_timestamp - features_timestamp`, nor require a
stale-data reason/block when freshness exceeds the runtime threshold.

Risk: future adapters could accept internally inconsistent model-service responses.

Expected fix: add optional runtime freshness threshold validation and require `recommended_action =
skip` with `stale_data` in `hard_risk_blocks` when the threshold is exceeded.

## Verification

Final CT-34 close-out before this audit had:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'python -m pip install --quiet -e ".[dev]" && python -m pytest && ruff check . && ruff format --check .'
```

Result: 30 tests passed, lint passed, format check passed.

## Backlog Created

Issues were created in YouTrack project `CT` for the findings above.

- `CT-78`: Expose out-of-sample baseline metrics as first-class reports.
- `CT-79`: Make OHLC target/stop same-bar ambiguity pessimistic or explicit.
- `CT-80`: Make backtest and meta-strategy exposure duration-aware.
- `CT-81`: Cross-check ML inference response freshness and stale-data blocks.
