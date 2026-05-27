# CT-147 No-TON Exit-Risk Variants

Date: 2026-05-27

Issue: CT-147

Epic: CT-113

## Decision

Rejected as a replacement for the CT-145 paper candidate.

The idea is valid strategy research: many historical entries do move favorably before failing to
reach the fixed `2R` target, so a breakeven or trailing stop can plausibly reduce full stop-outs.
However, on the current six-month no-TON candidate, the pre-declared dynamic exits did not improve
the selected candidate enough to replace the fixed `0.4%` stop / `0.8%` target / `12` bar horizon
model. CT-145 should continue forward paper collection unchanged.

This is research-only. No live order placement, leverage, margin, or runtime trade-state behavior
was changed.

## Baseline Candidate

Candidate inherited from CT-144 / CT-145:

- candidate: `ct144_no_ton`
- candidate symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`
- side: long
- entry filters: negative funding, non-weak close location, risk-on 1m and 5m context
- ranking: expected-R ridge, top `3`
- baseline exit: fixed stop `0.4%`, target `0.8%`, horizon `12` bars, `stop_first`

## Matrix

Config:

- `configs/ct147-no-ton-exit-risk-matrix.json`

Artifacts:

- `data/generated/ct147_no_ton_exit_risk_matrix/leaderboard.json`
- `data/generated/ct147_no_ton_exit_risk_matrix/leaderboard.md`
- per-variant `baseline_report.json`, `model_artifact.json`, `record.json`, and
  `stability_report.json` under `data/generated/ct147_*`

Variants:

- fixed h12 comparator;
- h12 breakeven after `+1R`;
- h12 breakeven after `+1R` with `+0.1R` lock;
- h12 breakeven plus `1.0R` trailing stop;
- h12 breakeven plus `1.5R` trailing stop;
- h24 breakeven with `+0.1R` lock;
- h24 breakeven plus `1.5R` trailing stop.

Dynamic exit semantics are conservative: each future bar checks the current stop first, then moves the
stop after favorable movement reaches the configured activation. If a move and retrace occur inside
the same OHLC bar, `stop_first` does not assume the stop could be moved before the adverse touch.

## Results

| Variant | Avg R | Rule Avg R | OOS trades | Max DD | Stability | Decision |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| fixed h12 comparator | `0.3959` | `-0.4591` | `275` | `1.60%` | `pass` | keep CT-145 |
| h12 breakeven | `0.0480` | `-0.1943` | `16` | `0.55%` | `reject` | reject: sparse |
| h12 breakeven +0.1R lock | `-0.0441` | `-0.1966` | `3000` | `1.61%` | `reject` | reject: negative |
| h12 breakeven + trail 1.0R | `-0.0899` | `-0.2102` | `247` | `0.42%` | `reject` | reject: negative |
| h12 breakeven + trail 1.5R | `-0.0292` | `-0.2027` | `14` | `0.20%` | `reject` | reject: sparse/negative |
| h24 breakeven +0.1R lock | `0.3211` | `-0.1987` | `17` | `0.42%` | `reject` | reject: sparse |
| h24 breakeven + trail 1.5R | `0.1725` | `-0.2137` | `31` | `0.47%` | `reject` | reject: sparse |

The only broad-sample dynamic variant, h12 breakeven with a `+0.1R` lock, produced `3000` OOS
trades but negative average R after costs. The positive dynamic variants stayed far below the
`>=100` OOS trade gate.

## Favorable-Then-Fail Cases

The user's hypothesis is real in the historical data:

| Scope | Count |
| --- | ---: |
| all fixed-outcome candidate labels | `20,175` |
| all candidates moved `>=0.5R`, missed `2R`, then lost | `3,829` |
| all candidates moved `>=1.0R`, missed `2R`, then lost | `1,577` |
| all candidates moved `>=1.5R`, missed `2R`, then lost | `743` |
| selected fixed h12 OOS trades | `275` |
| selected trades moved `>=0.5R`, missed `2R`, then lost | `67` |
| selected trades moved `>=1.0R`, missed `2R`, then lost | `38` |
| selected trades moved `>=1.5R`, missed `2R`, then lost | `23` |

For the `38` selected OOS trades that moved at least `+1R` before failing, the conservative h12
breakeven model still averaged `-0.7013R` after costs. With a `+0.1R` lock it averaged `-0.6539R`.
That is less bad than full fixed stop-outs in some cases, but it is not enough to improve the whole
candidate after costs and conservative OHLC ambiguity handling.

## Interpretation

The exit-management idea is not foolish. It is a real failure mode of fixed `2R` targets. The issue is
that the currently selected edge appears to depend on allowing enough winners to reach the fixed
target. Moving stops dynamically cuts some losers, but also clips or reshapes too many trades, and
the model's selected subset becomes either too sparse or negative.

CT-145 remains the better paper candidate:

- fixed h12 keeps `275` OOS trades;
- avg R remains materially higher at `0.3959`;
- max DD remains within gate at `1.60%`;
- stability remains `pass`;
- live trading remains unapproved pending forward evidence.

## Next Step

Do not replace CT-145 with a dynamic exit variant.

Useful follow-up is not another nearby trailing-stop parameter sweep. Instead, add counterfactual
exit telemetry to the CT-145 forward-paper review so actual live paper signals can report whether
they moved `+0.5R`, `+1R`, or `+1.5R` before closing. That would show whether the favorable-then-fail
pattern persists on new data without changing the paper candidate mid-stream.
