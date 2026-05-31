# CT-194 Spot Timing Layer Sweep (15m/30m/4h)

Status: CT-194 rejected.

## Thesis

Compare spot candlestick timing for the broad 17-coin drawdown-recovery strategy from CT-193:

- `15m`
- `30m`
- `4h`

The objective was to see whether cadence changes improve gate pass status without changing the core strategy design.

## Inputs

- Windows:
  - `2024H2` (`2024-07-01` → `2025-01-01`)
  - `2025H1` (`2025-01-01` → `2025-07-01`)
  - `2025JulNov` (`2025-07-01` → `2025-11-25`)
- Broad spot universe (`17` symbols): `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`, `DOTUSDT`, `LINKUSDT`, `NEARUSDT`, `APTUSDT`, `ARBUSDT`, `OPUSDT`, `INJUSDT`, `DOGEUSDT`.
- New/updated artifacts:
  - `scripts/download_binance_spot_klines.py` (adds `--period` CLI arg and period-aware dataset/manifest fields),
  - `tests/test_binance_spot_klines_script.py` (new `30m` dataset test),
  - `configs/ct194_spot_drawdown_swing_broad_rotation_15m.json`,
  - `configs/ct194_spot_drawdown_swing_broad_rotation_30m.json`,
  - `configs/ct194_spot_drawdown_swing_broad_rotation_4h.json`.

## Results

All rows failed the existing gates in every timeframe. Representative outputs:

### 15m

`portfolio_dd8_broad_spot_baseline_guard_1000`: `34` trades, `33` closed, `1` open, `Max DD -2.90%`, `Gate fail`.

Best closed-no-open row: `portfolio_dd8_broad_symbol_30d_partial_trail_1000`: `13` trades, `Avg closed 6.05%`, `Max DD -0.79%`, `Gate fail`.

### 30m

`portfolio_dd8_broad_spot_baseline_guard_1000`: `46` trades, `42` closed, `4` open, `Max DD -4.21%`, `Gate fail`.

`portfolio_dd8_broad_symbol_30d_partial_trail_1000`: `22` trades, `19` closed, `3` open, `Max DD -2.89%`, `Gate fail`.

### 4h

`portfolio_dd8_broad_spot_baseline_guard_1000`: `52` trades, `43` closed, `9` open, `Max DD -14.73%`, `Gate fail`.

`portfolio_dd8_broad_symbol_30d_partial_trail_1000`: `14` trades, `10` closed, `4` open, `Max DD -4.22%`, `Gate fail`.

## Decision

- No timeframe made CT-194 pass gates.
- Negative max drawdown + open inventory remained unresolved in all variants.
- Timing alone did not rescue this branch.
- Keep CT-113 active and move to a different spot entry/exhaustion hypothesis.

## Follow-Up: 5-Symbol Selected Timing Sweep

After the broad 17-symbol cadence rejection, we also reran the selected five-symbol CT-193 rows
(`SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`) across `2024H1`, `2024H2`, `2025H1`, and
`2025JulNov` using `15m`, `30m`, and `4h` true spot candles.

No-lookahead best rows:

| timeframe | best scenario | avg return | 2024H1 | 2024H2 | 2025H1 | 2025JulNov | avg max PnL DD | closed | open | gate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `15m` | `portfolio_dd8_symbol_30d_momentum_rotation_1000` | `1.13%` | `1.83%` | `2.29%` | `0.00%` | `0.42%` | `-0.75%` | `10` | `0` | fail |
| `30m` | `portfolio_dd8_spot_baseline_guard_1000` | `2.69%` | `2.05%` | `1.93%` | `3.63%` | `3.14%` | `-0.88%` | `25` | `0` | fail |
| `4h` | `portfolio_dd8_basket_14d_momentum_rotation_1000` | `2.03%` | `2.09%` | `4.71%` | `0.00%` | `1.31%` | `-0.89%` | `22` | `1` | fail |

We then ran a diagnostic oracle timing gate with `entry_profit_lookahead_hours` in
`{24, 48, 72, 120}`. This gate uses future candles and is not tradable; it only answers whether
better entry timing could plausibly rescue the current rule family.

Best oracle-lookahead row:

| timeframe | lookahead | best scenario | avg return | 2024H1 | 2024H2 | 2025H1 | 2025JulNov | avg max PnL DD | closed | open | gate |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `30m` | `120h` | `portfolio_dd8_spot_baseline_guard_1000` | `2.60%` | `1.71%` | `1.93%` | `3.63%` | `3.14%` | `-0.86%` | `24` | `0` | fail |

Follow-up decision:

- `30m` remains the cleanest selected cadence, but its best row is still far below the `+5%`
  average-window gate and far below the user's desired month-sized return profile.
- `15m` is too sparse, and `4h` keeps some unresolved inventory or inactive windows.
- Even the future-informed oracle timing gate fails, so CT-194 should not continue with nearby
  timing-threshold tuning inside this same spot drawdown/rotation rule family.

Generated outputs for traceability:

- `data/generated/ct194_spot_drawdown_swing_broad_rotation_15m/report.json`
- `data/generated/ct194_spot_drawdown_swing_broad_rotation_30m/report.json`
- `data/generated/ct194_spot_drawdown_swing_broad_rotation_4h/report.json`
- `data/generated/ct194_spot_broad_2024h2_15m_dataset/manifest.json` (+ `30m`, `4h` siblings)
- `data/generated/ct194_spot_broad_2025h1_15m_dataset/manifest.json` (+ `30m`, `4h` siblings)
- `data/generated/ct194_spot_broad_2025julnov_15m_dataset/manifest.json` (+ `30m`, `4h` siblings)
- `data/generated/ct193_spot_momentum_rotation_selected_15m_nolookahead_5sym/report.json`
- `data/generated/ct193_spot_momentum_rotation_selected_30m_nolookahead_5sym/report.json`
- `data/generated/ct193_spot_momentum_rotation_selected_4h_nolookahead_5sym/report.json`
- `data/generated/ct193_spot_momentum_rotation_selected_{15m,30m,4h}_lookahead{24,48,72,120}_5sym/report.json`
