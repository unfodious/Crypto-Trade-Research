# CT-105 Paper-Trading Pack Blocked

Date: 2026-05-26

## Decision

No paper-trading promotion pack is prepared for CT-96.

This is intentional. `templates/ml-promotion-checklist.v1.json` and
`docs/paper-trading-safety-plan.md` require a completed research-only promotion decision before any
fake-executor, paper-trading, shadow-mode, or pilot workflow. CT-104 selected no candidate because
all expanded CT-96 candidates were rejected.

## Why The Pack Must Not Exist

CT-105 acceptance says the pack must not exist for a rejected candidate. The current best available
candidate, `ct102_volume_long_continuation_h24`, is rejected:

- Model OOS average R: `-0.4576`
- Rule-only OOS average R: `-0.5360`
- Max drawdown: `99.9999%`
- Registry status: `reject`
- Stability status: `reject`

Preparing a paper-trading pack anyway would blur the boundary between research rejection evidence
and promotion evidence.

## Safety References

- Promotion checklist template: `templates/ml-promotion-checklist.v1.json`
- Paper-trading safety plan: `docs/paper-trading-safety-plan.md`
- Selection block: `docs/experiments/ct104-selection-blocked.md`
- Stability block: `docs/experiments/ct103-stability-drawdown-gates.md`
- CT-102 complementary setup matrix: `docs/experiments/ct102-complementary-expanded-matrix.md`
- CT-101 short-fade matrix: `docs/experiments/ct101-expanded-short-fade-matrix.md`

## Runtime Boundary

No runtime integration code is merged for CT-105.

The research model contract remains:

- ML outputs can recommend only `take` or `skip`.
- The Go runtime keeps authority over risk, sizing, leverage, order placement, reconciliation,
  kill switches, and exchange interaction.
- No live order authority is granted by CT-96 research outputs.

## Future Task Rule

Do not create a future runtime or paper-trading integration task from CT-96 unless a later research
candidate has:

- registry status `promote_to_paper_trading`,
- positive OOS expectancy after costs,
- rule-only and no-trade comparison evidence,
- acceptable drawdown,
- stability gates passed,
- artifact and registry records with exact research git commit,
- a completed promotion checklist.

At that point, the runtime/paper integration task must be separate and must use the Crypto Trade
trading-safety workflow before touching any Go runtime behavior.
