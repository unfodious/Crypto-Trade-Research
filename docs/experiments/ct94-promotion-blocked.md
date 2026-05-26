# CT-94 Paper-Trading Promotion Decision

Date: 2026-05-26

Decision: blocked, no paper-trading promotion pack created.

## Source Evidence

- CT-91 first real futures baseline: `configs/ct91-real-baseline-experiment.json`
- CT-93 iteration notes: `docs/experiments/ct93-iteration-notes.md`
- Best CT-93 candidate config: `configs/ct93-short-fade-range-position.json`
- Best candidate registry record:
  `data/generated/experiment_registry/ct93_short_fade_range_position/20260526T083300Z/record.json`
- Best candidate checklist:
  `data/generated/ct93_short_fade_range_position/promotion_checklist.json`
- Best candidate model artifact:
  `data/generated/ct93_short_fade_range_position/model_artifact.json`
- Model artifact hash:
  `78cefaca878aa19c05286798a014ad70eb8274a0b19ebedde736e86442a66a83`

Generated `data/generated/` files are local ignored evidence artifacts and are not committed.

## Best Candidate Summary

Candidate: `ct93_short_fade_range_position`

Setup: deterministic high-range short fade.

Label: short, 12 bars, 2R target, 1R stop, costs included.

Decision feature: `range_position_20`

Dataset: CT-88 one-day BTCUSDT/ETHUSDT USD-M futures 1m dataset.

Chronological split:

- train through `2025-07-01T12:00:00Z`
- validation through `2025-07-01T18:00:00Z`
- test through `2025-07-02T00:00:00Z`

Out-of-sample metrics:

| Metric | Model | Rule-only |
| --- | ---: | ---: |
| Trades | 29 | 31 |
| Average R | 0.8940 | 0.8573 |
| Total return | 29.09% | 29.90% |
| Max drawdown | 10.09% | 10.09% |

The model beats rule-only average R after costs, but it does not pass the full promotion gate set.

## Failed Gates

The best candidate remains `reject` because:

- `drawdown_within_limits`: max drawdown is `10.09%`, above the configured `8%` research limit.
- `stability_checks_pass`: evidence covers only one day and does not prove stability across days,
  symbols, sessions, or nearby thresholds.
- `paper_trading_plan_exists`: no paper-trading plan should exist until the research gates pass.

The failed gates are substantive. They are not documentation chores to bypass.

## Paper-Trading Pack Status

No completed paper-trading pack is created for CT-94 because the candidate did not pass promotion
gates. Creating a paper-trading package now would make the rejected one-day result look more
actionable than it is.

The reusable safety template remains `templates/ml-promotion-checklist.v1.json`, but it is not
filled for this candidate. The paper-trading safety path in `docs/paper-trading-safety-plan.md`
still applies to any future passing candidate.

## Runtime Boundary

No runtime integration is authorized by CT-94.

For any future passing candidate:

- model output may recommend only `take` or `skip`
- Go runtime owns account state, risk sizing, leverage, stops, take profit, order placement,
  kill switches, and exchange reconciliation
- stale data, stale model, missing feature, exchange/API error, reconciliation drift, and operator
  pause must hard-block model influence
- no live credentials, decrypted secrets, authorization headers, or exchange request signatures may
  appear in research artifacts or logs
- a separate YouTrack task with trading-safety review is required before paper or runtime work

## Required Next Evidence

Before reopening promotion:

1. Expand the dataset beyond the current one-day CT-88 sample.
2. Rerun the high-range short fade setup across multiple days and market sessions.
3. Check sensitivity across nearby `range_position_20` thresholds and probability thresholds.
4. Compare BTCUSDT and ETHUSDT behavior separately and together.
5. Keep the chronological split discipline; do not shuffle or tune against the current test window.
6. Require max drawdown to pass the configured gate before any paper-trading pack is completed.

## Follow-Up Task Policy

No runtime or paper-trading implementation task is created from CT-94 because there is no promoted
candidate. A future task should be created only after a candidate has a registry decision of
`promote_to_paper_trading` and a completed promotion checklist.
