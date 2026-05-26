# CT-120 H12 Pocket Stability Matrix

Date: 2026-05-26

YouTrack: CT-120

Parent epic: CT-113

Research commit: `ad6bc78`

## Purpose

CT-120 followed the CT-119 controlled reject. CT-119 found a small positive h12 risk-controlled
pocket, but it had only `27` OOS trades against the configured minimum of `100`. CT-120 tested whether
nearby candidate filters and a top-N proxy could increase trade count while preserving positive
average R and drawdown control.

## Setup

- Dataset: `data/generated/ct96_expanded_core_futures_dataset/manifest.json`
- Rows loaded: `1,425,600`
- Feature set: `features.ct120.multifeature-context.v1`
- Model type: `multifeature_ridge`
- Label: long, 12-bar horizon, 2R target, stop-first tie breaker
- Risk controls: `max_trades_per_symbol=200`, `max_trades_per_decision_time=3`, `loss_cooldown_signals=2`
- Top-N proxy row: `max_trades_per_decision_time=5`
- Train end: `2026-04-25T00:00:00Z`
- Validation end: `2026-05-10T00:00:00Z`
- Test end: `2026-05-25T00:00:00Z`

## Matrix Results

| Experiment | Decision | Avg R | Rule Avg R | Trades | Max DD | Failed gates |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `ct120_h12_pocket_vol13_close70_risk50` | reject | 0.0472 | -0.5582 | 27 | 4.40% | minimum trade count, stability, paper plan |
| `ct120_h12_pocket_vol12_close65_risk50` | reject | 0.6250 | -0.5661 | 5 | 1.58% | minimum trade count, stability, paper plan |
| `ct120_h12_pocket_vol11_close65_risk45` | reject | -0.2926 | -0.5774 | 986 | 83.07% | edge, walk-forward, drawdown, stability, paper plan |
| `ct120_h12_pocket_vol10_close60_risk45` | reject | -0.2188 | -0.5783 | 1120 | 78.47% | edge, walk-forward, drawdown, stability, paper plan |
| `ct120_h12_pocket_vol11_close60_risk40_top5` | reject | -0.3183 | -0.5680 | 1089 | 88.43% | edge, walk-forward, drawdown, stability, paper plan |
| `ct120_h12_pullback_vol13_low30_risk50` | reject | -0.2750 | -0.5024 | 10 | 3.09% | edge, walk-forward, minimum trade count, stability, paper plan |
| `ct120_h12_pullback_vol11_low35_risk45` | reject | -0.1036 | -0.5384 | 112 | 13.23% | edge, walk-forward, drawdown, stability, paper plan |

## Interpretation

The CT-119 positive pocket did not survive adjacent-threshold expansion. Loosening filters increased
candidate sample count and OOS trade count, but the model moved into negative expectancy and drawdown
failure. The more selective `vol12_close65_risk50` row showed high average R but only `5` OOS trades,
so it is not actionable evidence.

The pullback/fade comparison did not rescue the setup. The broader pullback row reached `112` OOS
trades, but remained negative and exceeded the drawdown gate.

## Decision

Do not promote CT-120 to paper trading. Keep CT-113 open.

The next research step should not simply loosen filters further. CT-120 indicates a sparse,
threshold-sensitive pocket. The next hypothesis should test whether model probability calibration,
ranking/top-N selection, and regime-specific validation can separate the positive strict pocket from
the high-trade-count negative regions.

Recommended CT-121 direction:

- Add explicit probability-threshold and top-N ranking sweeps, not only candidate-filter sweeps.
- Report validation-selected threshold versus OOS trade count and average R.
- Stratify the h12 pocket by BTC/ETH shock, market breadth, and volatility bucket.
- Consider extending historical data before accepting or rejecting a sparse positive pocket.
- Keep promotion gates unchanged: positive after costs, >=100 OOS trades, drawdown within limits,
  leakage-safe, and stability-proven.

Backtest results are research evidence only, not live trading approval.
