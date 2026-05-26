# CT-119 Controlled Multifeature Matrix

Date: 2026-05-26

YouTrack: CT-119

Parent epic: CT-113

Research commit: `6e27529`

## Purpose

CT-119 tested the first controlled multifeature market-context matrix after CT-107 rejected the
single-feature baseline. The goal was to keep the richer CT-113 thesis intact while checking whether
technical indicators, market context, multi-feature ridge scoring, and risk controls produce a
candidate strong enough for paper-trading preparation.

## Dataset And Setup

- Dataset: `data/generated/ct96_expanded_core_futures_dataset/manifest.json`
- Rows loaded: `1,425,600`
- Symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`, `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`
- Timeframe: `1m`
- Feature set: `features.ct119.multifeature-context.v1`
- Model type: `multifeature_ridge`
- Candidate setup: `context_breakout_long`
- Filters:
  - `volatility_expansion_20 >= 1.3`
  - `close_location >= 0.7`
  - `risk_on_score_20 >= 0.5`
- Train end: `2026-04-25T00:00:00Z`
- Validation end: `2026-05-10T00:00:00Z`
- Test end: `2026-05-25T00:00:00Z`

## Matrix Results

| Experiment | Decision | Avg R | Rule Avg R | Trades | Max DD | Failed gates |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `ct119_context_breakout_h24` | reject | -0.0987 | -0.5268 | 131 | 10.76% | edge, walk-forward, drawdown, stability, paper plan |
| `ct119_context_breakout_risk_h24` | reject | -0.2166 | -0.5268 | 1321 | 82.57% | edge, walk-forward, drawdown, stability, paper plan |
| `ct119_context_breakout_risk_h12` | reject | 0.0472 | -0.5582 | 27 | 4.40% | minimum trade count, stability, paper plan |
| `ct119_context_breakout_top1_h24` | reject | -0.0500 | -0.5268 | 48 | 5.64% | edge, walk-forward, minimum trade count, stability, paper plan |

The best row was `ct119_context_breakout_risk_h12`. It beat the rule-only and single-feature
comparators after costs, stayed within drawdown limits, and passed leakage gates. It did not pass
promotion because OOS sample size was too small: `27` trades versus the configured minimum of `100`.
Stability checks also remain intentionally false until a broader matrix proves the edge is not a
single fragile parameter optimum.

## Runtime Finding

The first CT-119 attempt exposed a feature-generation performance bug: MACD recomputed the full
symbol history for every row. The generator now computes only the trailing MACD values needed by the
signal window, preserving the same point-in-time calculation while making the expanded matrix
practical to run.

Batch input caching was also added so matrix rows reuse source rows, features, and matching labels
when only risk controls or output paths change.

## Decision

Do not promote CT-119 to paper trading. Keep CT-113 open.

CT-119 is useful evidence because it shows that the enriched feature/model stack can find a small
positive h12 risk-controlled pocket, but it is not yet a working candidate. The next research step
should expand the positive pocket enough to reach minimum OOS trade count while retaining positive
average R and drawdown control.

Recommended CT-120 direction:

- Keep h12 as the first branch.
- Sweep candidate filters around `volatility_expansion_20`, `close_location`, and `risk_on_score_20`
  to raise OOS trades above `100`.
- Add side-by-side threshold stability checks before any paper-trading plan.
- Compare long breakout with a mean-reversion/fade branch using the same multifeature stack.
- Add explicit top-N ranking experiments instead of fixed take/skip only.

Backtest results are research evidence only, not live trading approval.
