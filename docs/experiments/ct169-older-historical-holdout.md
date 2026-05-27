# CT-169 Older Historical Holdout

Status: evidence added; no live approval.

CT-169 adds an older, pre-selection historical holdout for the CT-145 no-TON and CT-156 high-beta
plus DOT paper candidates. The goal is not to retrain or recalibrate. The test replays the already
selected paper packs against older data and checks whether the thesis survives outside the original
six-month experiment window.

## Data

- OHLCV source: Binance USD-M futures 1m candles imported through the backend historical importer.
- Holdout window: `2025-07-01T00:01:00Z` through `2025-11-25T00:00:00Z`.
- Symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`,
  `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`.
- OHLCV rows: `2,328,480`.
- Funding rows: `5,303`.
- OHLCV manifest: `data/generated/ct169_older_holdout_core_futures_dataset/manifest.json`.
- Funding manifest: `data/generated/ct169_older_holdout_funding_rate_dataset/manifest.json`.

The older import exposed a valid crypto flash-crash candle on `AVAXUSDT` at
`2025-10-10T21:23:00Z`. The previous ingestion guard rejected intraminute ranges above 50% of open
price. Neighboring rows showed this was part of the October 10 crash/rebound sequence rather than a
single corrupt tick, so the guard was relaxed to reject ranges above 100% instead.

## Method

Replay runner: `crypto-trade-run-historical-holdout-replay`.

Config: `configs/ct169-older-holdout-replay.json`.

Replay rules:

- use frozen pack manifests from CT-145 and CT-156;
- generate the same `features.ct138.regime-symbol-refinement.v1` feature set;
- apply the existing negative-funding/risk-on candidate filters;
- score with the frozen `expected_r_model`;
- keep the frozen expected-R threshold and top-3 per decision time;
- evaluate 12-bar long labels with the same `0.4%` stop, `0.8%` target, stop-first tie breaker,
  and `0.07%` round-trip cost assumption;
- apply the same research risk controls in the backtest layer.

No training, validation threshold selection, symbol re-selection, or filter tuning was performed on
this older holdout.

## Results

| Candidate | Holdout trades | Avg R | Max DD | Profit factor | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| CT-145 no-TON | 1,255 | 0.0287 | 4.34% | 1.0558 | survives, still weak |
| CT-156 high-beta + DOT | 672 | 0.0716 | 8.32% | 1.1248 | watch only; DD gate miss |

CT-145 accepted-trade symbol slices:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| ADAUSDT | 226 | 0.0716 |
| AVAXUSDT | 188 | -0.0299 |
| ICPUSDT | 399 | 0.1008 |
| SOLUSDT | 229 | -0.0797 |
| SUIUSDT | 213 | 0.0161 |

CT-156 accepted-trade symbol slices:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| ADAUSDT | 105 | 0.1434 |
| AVAXUSDT | 68 | -0.0240 |
| DOTUSDT | 61 | -0.2664 |
| ICPUSDT | 260 | 0.1690 |
| SOLUSDT | 82 | -0.2101 |
| SUIUSDT | 96 | 0.2526 |

Session slices were positive for both candidates after risk controls. The selected rows before risk
controls are also written for audit, but the headline metrics above use accepted backtest trades.

Artifacts:

- `data/generated/ct169_older_holdout_replay/replay_report.json`;
- `data/generated/ct169_older_holdout_replay/replay_report.md`;
- `data/generated/ct169_older_holdout_replay/ct145_no_ton_negative_funding_paper_pack/accepted_trades.parquet`;
- `data/generated/ct169_older_holdout_replay/ct156_high_beta_dot_shadow_paper_pack/accepted_trades.parquet`.

## Interpretation

The older holdout is materially better evidence than the previous single-month OOS slice because it
adds July-November 2025, including the October 10 crash. The candidates did not collapse on older
data, which supports continuing research and paper observation.

This is still not a working model approval:

- CT-145 has positive but thin expectancy (`0.0287R`) and only 3 of 5 symbols positive.
- CT-156 has better expectancy (`0.0716R`) but misses the drawdown gate at `8.32%` and DOT remains
  strongly negative.
- Both remain backtest evidence only. Forward paper evidence is still required before any runtime
  promotion discussion.

## Next Step

Keep CT-113 open. Continue paper tracking for CT-145 and CT-156. Created CT-170 to cache generated
CT-169 feature frames so older-holdout replays do not repeatedly spend several minutes and tens of GB
of RAM rebuilding identical features.
