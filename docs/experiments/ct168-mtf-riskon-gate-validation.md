# CT-168 MTF Risk-On Gate Validation

Date: 2026-05-27

Issue: CT-168

Epic: CT-113

## Goal

CT-167 showed that CT-145 and CT-156 forward-paper streams currently emit zero candidates because
`mtf_5m_risk_on_score_20 >= 0.35` rejects every otherwise eligible latest row. CT-168 tested
whether that 5m MTF risk-on gate should be removed, loosened, or retained.

This was a historical/OOS counterfactual matrix. The live paper packs were not changed.

## Matrix

Two candidate universes were tested:

- no-TON: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`;
- high-beta plus DOT: the same symbols plus `DOTUSDT`.

Each universe was tested with four MTF gate variants:

- current gate: `mtf_5m_risk_on_score_20 >= 0.35`;
- no MTF gate;
- loose gate: `mtf_5m_risk_on_score_20 >= 0.15`;
- middle gate: `mtf_5m_risk_on_score_20 >= 0.25`.

All rows kept the same negative-funding, funding z-score, close-location, local risk-on,
expected-R ranking, cost, split, and risk-control assumptions as the current paper candidates.

## Results

| Experiment | Avg R | Rule Avg R | OOS Trades | Max DD | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| `ct168_no_ton_mtf035_current_top3` | 0.3959 | -0.4591 | 275 | 1.60% | reject |
| `ct168_no_ton_no_mtf_gate_top3` | 0.3162 | -0.5477 | 171 | 1.26% | reject |
| `ct168_no_ton_mtf015_top3` | 0.2432 | -0.5067 | 110 | 1.72% | reject |
| `ct168_no_ton_mtf025_top3` | 0.4384 | -0.4837 | 119 | 1.72% | reject |
| `ct168_high_beta_dot_mtf035_current_top3` | 0.4665 | -0.4843 | 106 | 1.47% | reject |
| `ct168_high_beta_dot_no_mtf_gate_top3` | 0.3461 | -0.5764 | 142 | 1.63% | reject |
| `ct168_high_beta_dot_mtf015_top3` | 0.5125 | -0.5359 | 96 | 1.26% | reject |
| `ct168_high_beta_dot_mtf025_top3` | 0.4500 | -0.5125 | 96 | 1.37% | reject |

All rows remain formally rejected because the baseline runner's promotion record does not attach
the external stability artifact or paper-trading plan. Existing detailed stability artifacts for
the equivalent current-gate candidates are still relevant:

- no-TON current gate: stability `pass`;
- high-beta plus DOT current gate: stability `pass`, but `DOTUSDT` remains a weak negative slice.

## Interpretation

The 5m MTF risk-on gate should not be removed based on this evidence.

For the no-TON universe, the current `>= 0.35` gate has more OOS trades than the no-gate and loose
gate variants while keeping positive average R and low drawdown. The `>= 0.25` variant has higher
average R but only 119 OOS trades, so it is more fragile.

For the high-beta plus DOT universe, the current `>= 0.35` gate is the only tested MTF-gated DOT
variant that clears the 100-trade floor. Removing the MTF gate increases trade count but reduces
average R. The looser `>= 0.15` and `>= 0.25` gates have strong average R but miss the 100-trade
floor.

CT-167's zero forward candidates are therefore best interpreted as current-market scarcity: the
latest 5m market context is not risk-on enough for these packs. That is a feature of the gate, not
yet evidence that the gate is broken.

## Decision

Keep CT-145 and CT-156 paper-pack filters unchanged.

No working model or live trading approval is claimed. Continue forward-paper collection and use
new unseen data as the post-selection validation layer. Historical data remains useful for
counterfactual rejection and filter validation, but it cannot fully replace forward evidence after
we have already selected and refined a candidate on history.

## Safety

CT-168 is research-only. It does not place, cancel, resize, or close orders; it does not change
leverage, stops, take-profit handling, or Binance runtime behavior.
