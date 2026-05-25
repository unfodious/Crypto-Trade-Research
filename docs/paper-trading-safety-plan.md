# ML Paper-Trading Safety Plan

Checklist template: `templates/ml-promotion-checklist.v1.json`

This plan defines the only acceptable path from research evidence to any future ML-assisted runtime
influence. CT-45 does not grant live order authority and does not modify runtime behavior.

## Promotion Checklist

Every candidate must complete these stages in order:

1. `research_only`: complete experiment record, baseline comparison, walk-forward report, leakage
   check, stability check, and reviewed promotion decision.
2. `fake_executor_replay`: deterministic historical replay using `ml-inference.v1`, no live
   credentials, and replay metrics matching research within tolerance.
3. `paper_trading_dry_run`: live data with no real orders, paper fills/fees, daily operator review,
   and no secret leaks in logs.
4. `shadow_mode`: model recommendations logged separately from current strategy decisions with a
   disagreement report.
5. `tiny_size_pilot`: blocked until explicit human approval, a separate safety-reviewed
   implementation issue, and runtime tests exist.

Every stage has `live_order_authority=false` in the checklist. A real-money pilot requires a new
issue and trading-safety review.

## Risk Controls

Required controls before live influence:

- max daily loss: default `2R`
- max weekly loss: default `4R`
- max monthly loss: default `6R`
- max open positions: default `1`
- symbol exposure cap
- BTC/ETH beta exposure cap
- leverage cap owned by runtime rules, independent of model confidence
- kill switch
- stale data/model block
- missing feature block
- exchange/API error block
- reconciliation drift block

If several positions share the same BTC/ETH or symbol failure mode, treat them as one portfolio
risk bucket.

## Paper Metrics

Paper trading must mirror research metrics as closely as possible:

- average R
- profit factor
- trade count
- max drawdown depth and duration
- win/loss asymmetry
- turnover
- rejection reason distribution

Differences between research and paper assumptions must be recorded before promotion review.

## Logging

Logs must be secret-free and include:

- model id and version
- signal timestamp
- features timestamp
- recommended action
- expected R
- target-before-stop probability
- confidence
- reason codes
- hard risk blocks
- runtime decision
- paper fill id when applicable

Never log API keys, tokens, encrypted payloads, decrypted credentials, authorization headers, or raw
exchange request signatures.

## Rollback

Disable ML influence immediately when any of these occur:

- daily, weekly, or monthly loss limit is hit
- stale data/model blocks repeat
- state reconciliation drift appears
- unexpected live order authority is detected
- operator confidence is lost

Rollback actions:

1. Disable ML influence.
2. Keep read-only reconciliation running if healthy.
3. Preserve logs and signal files.
4. Open an incident or follow-up issue.
5. Require operator approval before resuming.
