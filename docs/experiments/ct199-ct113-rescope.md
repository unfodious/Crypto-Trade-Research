# CT-199 CT-113 Re-Scope After Spot Drawdown Rejection

Date: 2026-05-31

Issue: CT-199

Epic: CT-113

Status: re-scope decision; no working model and no live-trading approval

## Why This Exists

CT-195, CT-196, CT-197, and CT-198 tested the same broad spot idea from several angles:

- wait for confirmed reversal/breakout after drawdown;
- exit stale or failed breakouts faster;
- require kline-level taker-flow pressure;
- inspect targeted raw Spot `aggTrades` around candidate entries.

The family did not produce a robust paper-trading candidate. The positive pockets were either too
sparse, fragile across windows, or made worse by flow filters. CT-199 therefore stops the local
threshold-sweep loop and asks what should happen next.

## Droplet Forward-Paper State

Droplet: `209.38.188.101`

Latest audited readiness timestamp: `2026-05-31T12:54:58Z`

Forward streams:

- `ct145_no_ton_negative_funding_forward_paper`
- `ct156_high_beta_dot_shadow_forward_paper`
- `ct184_adaptive_sizing_shadow_forward_paper`

Current aggregate:

- cumulative signals: `47`
- closed paper trades: `0`
- open paper trades: `0`
- live trading approved: `false`
- working model: `false`
- readiness: `not_ready`

All observed forward signals were skipped by the expected-R gate. That raised one useful diagnostic
question: is the gate too strict, or is it correctly preventing bad trades?

## CT-199 Skipped-Signal Counterfactual

Command:

```sh
crypto-trade-build-forward-skip-counterfactual \
  --config configs/ct199-forward-skip-counterfactual.json
```

Input signals were copied from the droplet forward-paper streams. The diagnostic does not modify
`forward_ledger.json`, does not create paper fills, and does not relax paper/live gates.

Result:

| Scope | Signals | Closed | Avg R | Median R | Win rate | Exit reasons |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Aggregate | `47` | `47` | `-0.2731` | `-0.1750` | `34.04%` | `39 horizon`, `8 stop` |
| CT-145 | `25` | `25` | `-0.3437` | `-0.2804` | `28.00%` | `20 horizon`, `5 stop` |
| CT-156 | `21` | `21` | `-0.2093` | `-0.1750` | `38.10%` | `18 horizon`, `3 stop` |
| CT-184 | `1` | `1` | `+0.1550` | `+0.1550` | `100.00%` | `1 horizon` |

Interpretation:

- The expected-R gate is not obviously too strict on the observed forward sample.
- The skipped population is negative after costs.
- None of the skipped signals reached the fixed target in the standard 12-bar exit model.
- CT-184 has only one skipped signal, so its positive single-signal counterfactual is not evidence.

## Re-Scope Decision

Do not continue CT-113 by:

- adding more nearby spot drawdown/breakout entry filters;
- loosening expected-R thresholds in live or paper streams;
- treating skipped-signal counterfactuals as paper evidence;
- promoting CT-145, CT-156, CT-184, or the spot drawdown family.

Continue CT-113 by separating two tracks:

1. Keep the droplet forward collectors running unchanged. They are useful data collection, but not
   a working model.
2. Start the next hypothesis from a different economic mechanism rather than another local entry
   tweak.

Recommended next branch:

Build a market-regime/relative-strength rotation test that uses the external feature families already
being collected, but validates them historically before changing paper streams. The question should be
whether external crowding/OI/order-book/liquidation context can identify when relative-strength
rotation is worth holding inventory, not whether one more micro-entry filter rescues the old setup.

## Artifacts

- `configs/ct199-forward-skip-counterfactual.json`
- `src/crypto_trade_research/forward_skip_counterfactual.py`
- `tests/test_forward_skip_counterfactual.py`
- generated local report:
  `data/generated/ct199_forward_skip_counterfactual/report.json`
- generated local markdown:
  `data/generated/ct199_forward_skip_counterfactual/report.md`

Generated reports are research artifacts and are not committed.

## Decision

CT-199 re-scopes CT-113 away from the rejected spot drawdown/filter-tuning loop. CT-113 remains open.
No paper-trading promotion, working-model claim, or live-trading approval.
