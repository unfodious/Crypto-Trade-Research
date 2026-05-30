# CT-193 Spot Drawdown Exhaustion Swing

Status: active research; no paper candidate yet.

CT-193 tested a different user hypothesis from the futures-continuation research: spot coins often
swing roughly `+/-10%` over several days, so buying exhausted drawdowns and selling profitable
rebounds may be more practical than chasing futures continuation.

This first screen uses existing USD-M futures OHLCV as a price-action proxy because no local spot
OHLCV dataset is currently available. A true spot candidate still requires spot candles and spot fee
validation.

## Thesis

The spot-style hypothesis was:

- buy only after a meaningful drawdown from a local high;
- require evidence that downside momentum is weakening, such as RSI rebound, close reclaim, and
  lower-wick rejection;
- never sell in loss;
- sell only when the position is profitable and the rebound starts fading;
- treat unresolved losers honestly as open/unrealized drawdown, not as disappeared losses.

## Method

Input windows:

- `2024H2`: `2024-07-01` to `2025-01-01`
- `2025H1`: `2025-01-01` to `2025-07-01`
- `2025JulNov`: `2025-07-01` to `2025-11-25`

Symbols:

- `SOLUSDT`
- `SUIUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `ICPUSDT`

Rules:

- aggregate existing 1m OHLCV to 1h bars;
- apply round-trip spot-style cost assumption of `0.20%`;
- enter after `8-12%` drawdown from local highs plus exhaustion/reclaim filters;
- exit only in profit when rebound fades;
- if a position never gets a profitable exit by the end of the window, keep it open and report
  unrealized PnL.
- for portfolio-DCA scenarios, start with `$1000` cash, use small first entries, add only at deeper
  drawdown bands, cap allocation per symbol, and mark open inventory to market.
- for market-guard DCA scenarios, allow entry/add only when the equal-weight basket has bounced
  from its recent low and most symbols show short-term recovery.

Artifacts:

- `configs/ct193-spot-drawdown-swing.json`
- `configs/ct193-spot-drawdown-swing-spot.json`
- `configs/ct193-spot-drawdown-swing-spot-bear-guard-selected.json`
- `configs/ct193-spot-drawdown-swing-spot-partial-trailing-selected.json`
- `configs/ct193-spot-drawdown-swing-spot-momentum-rotation-selected.json`
- `scripts/download_binance_spot_klines.py`
- `data/generated/ct193_spot_drawdown_swing/report.json`
- `data/generated/ct193_spot_drawdown_swing/report.md`
- `data/generated/ct193_spot_drawdown_swing_spot/report.json`
- `data/generated/ct193_spot_drawdown_swing_spot/report.md`

## Results

### One-Shot Entries

| Scenario | Trades | Closed | Open | Avg MTM | Avg Closed | Open Unrealized | Win Rate | PF | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `dd10_rsi_reclaim_5pct` | `121` | `106` | `15` | `-0.18%` | `4.41%` | `-32.58%` | `87.60%` | `0.9559` | fail |
| `dd8_fast_reclaim_3pct` | `171` | `156` | `15` | `0.31%` | `3.55%` | `-33.49%` | `91.23%` | `1.1039` | fail |
| `dd12_wick_capitulation_8pct` | `87` | `72` | `15` | `0.04%` | `6.81%` | `-32.41%` | `82.76%` | `1.0079` | fail |
| `dd12_wick_trend_guard_8pct` | `76` | `61` | `15` | `-1.26%` | `6.35%` | `-32.18%` | `80.26%` | `0.8022` | fail |
| `dd10_reclaim_trend_guard_5pct` | `115` | `100` | `15` | `-0.40%` | `4.53%` | `-33.23%` | `86.96%` | `0.9084` | fail |
| `dd8_confirmed_reversal_3pct` | `100` | `88` | `12` | `-0.54%` | `3.51%` | `-30.22%` | `88.00%` | `0.8520` | fail |
| `dd10_confirmed_reversal_5pct` | `16` | `14` | `2` | `2.36%` | `5.84%` | `-21.98%` | `87.50%` | `1.8600` | fail |
| `dd12_rebase_confirmed_8pct` | `5` | `3` | `2` | `-14.33%` | `0.59%` | `-36.72%` | `60.00%` | `0.0240` | fail |

The stricter confirmed-reversal branch improved entry quality but became sparse. The best one-shot
screen, `dd10_confirmed_reversal_5pct`, had positive mark-to-market but only `16` positions.

### Portfolio DCA

| Scenario | Avg Window Return | 2024H2 | 2025H1 | 2025JulNov | Closed | Open | Avg Closed | Open Unrealized | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd8_confirmed_dca_1000` | `5.21%` | `20.13%` | `-4.04%` | `-0.44%` | `61` | `6` | `5.83%` | `-17.96%` | fail |
| `portfolio_dd10_confirmed_dca_1000` | `5.64%` | `6.49%` | `14.77%` | `-4.35%` | `49` | `5` | `6.42%` | `-13.53%` | fail |
| `portfolio_dd8_dca_market_guard_1000` | `5.70%` | `3.97%` | `9.24%` | `3.90%` | `29` | `1` | `6.71%` | `-7.21%` | fail |
| `portfolio_dd8_market_guard_stable_1000` | `4.60%` | `5.24%` | `4.32%` | `4.24%` | `35` | `2` | `6.71%` | `-13.92%` | fail |
| `portfolio_dd10_market_guard_aggressive_1000` | `7.68%` | `9.98%` | `10.52%` | `2.53%` | `28` | `2` | `6.22%` | `-11.51%` | fail |

Portfolio-DCA settings:

- total cash cap: `$1000` per replay window;
- first entry: `$100`;
- `portfolio_dd8_confirmed_dca_1000`: add `$100` at `-8%`, `-16%`, and `-24%` from average cost,
  max `$300` per symbol;
- `portfolio_dd10_confirmed_dca_1000`: add `$125` at `-10%` and `-20%` from average cost, max
  `$350` per symbol;
- sell only when the average position is profitable and rebound momentum fades.

Market-guard additions:

- require the equal-weight basket to bounce at least `3%` from its recent `72h` low;
- require the basket to be positive over the last `12h`;
- require at least `60%` of symbols to be rising over the same `12h` window;
- cap concurrent open symbols to `3-4`, depending on the scenario.

Buy-and-hold context was extremely regime-dependent:

- `2024H2` equal-weight proxy return: `+117.25%`
- `2025H1` equal-weight proxy return: `-37.91%`
- `2025JulNov` equal-weight proxy return: `-23.75%`

### True Spot Replay

The follow-up replay replaced the USD-M futures OHLCV proxy with Binance Data Vision spot monthly
1h klines for the same symbols and windows. Data generation succeeded without missing slices:

- `ct193_spot_2024h2_dataset`: `22,080` rows
- `ct193_spot_2025h1_dataset`: `21,720` rows
- `ct193_spot_2025julnov_dataset`: `17,640` rows

The Data Vision timestamp format changes between older millisecond files and newer microsecond
files, so `scripts/download_binance_spot_klines.py` normalizes both units before writing the
research manifest.

| Scenario | Avg Window Return | 2024H2 | 2025H1 | 2025JulNov | Avg Max DD | Closed | Open | Avg Closed | Open Unrealized | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd8_dca_market_guard_1000` | `3.80%` | `4.67%` | `9.21%` | `-2.49%` | `-5.14%` | `31` | `2` | `6.58%` | `-15.38%` | fail |
| `portfolio_dd8_market_guard_stable_1000` | `2.65%` | `5.81%` | `4.28%` | `-2.15%` | `-7.78%` | `37` | `3` | `6.31%` | `-17.13%` | fail |
| `portfolio_dd10_market_guard_aggressive_1000` | `3.76%` | `9.64%` | `10.44%` | `-8.80%` | `-18.51%` | `26` | `3` | `7.80%` | `-15.08%` | fail |

Monthly marked-to-market returns show why the true spot replay is not promotable:

- `portfolio_dd8_dca_market_guard_1000`: worst months were `2025-08` at `-1.46%`, `2025-09` at
  `-1.88%`, and `2025-10` at `-7.25%`; `2025-11` rebounded `+8.52%`.
- `portfolio_dd8_market_guard_stable_1000`: worst months were `2025-02` at `-4.64%`, `2025-10` at
  `-6.90%`; `2025-11` rebounded `+8.48%`.
- `portfolio_dd10_market_guard_aggressive_1000`: worst months were `2025-02` at `-13.72%`,
  `2025-03` at `-6.38%`, and `2025-11` at `-9.41%`; its `2025H1` path had a `-39.08%` portfolio
  drawdown despite ending that window positive.

True spot replay therefore weakens the futures-proxy pocket. The broad-market guard still helps
avoid many bad entries, but it does not satisfy the user's objective of roughly month-sized strong
positive returns with acceptable inventory drawdown.

### Bear-Leg Abstention Replay

The next CT-193 follow-up tested whether the losing spot windows were caused by buying a temporary
bounce inside a larger downtrend. The added filters are point-in-time only:

- symbol-level trend guard: the coin must not be down more than a configured threshold over the
  prior `7d`, `14d`, or `30d`;
- basket-level trend guard: the equal-weight basket must not be down more than a configured
  threshold over the prior `7d`, `14d`, or `30d`;
- optional DCA trend guard: prevent adding when the coin itself is still in a larger bear leg.

Selected true-spot results:

| Scenario | Avg Window Return | 2024H2 | 2025H1 | 2025JulNov | Avg Max DD | Closed | Open | Open Unrealized | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd8_spot_baseline_guard_1000` | `3.80%` | `4.67%` | `9.21%` | `-2.49%` | `-5.14%` | `31` | `2` | `-15.38%` | fail |
| `portfolio_dd8_basket_7d_bear_abstain_1000` | `3.15%` | `3.03%` | `6.17%` | `0.24%` | `-4.38%` | `19` | `1` | `-18.95%` | fail |
| `portfolio_dd8_basket_14d_strict_bear_abstain_1000` | `2.34%` | `2.47%` | `0.33%` | `4.22%` | `-3.73%` | `11` | `0` | `0.00%` | fail |
| `portfolio_dd8_symbol_30d_strict_bear_abstain_1000` | `2.36%` | `4.11%` | `0.33%` | `2.65%` | `-4.49%` | `14` | `0` | `0.00%` | fail |

Interpretation:

- Bear-leg abstention fixed the obvious `2025JulNov` negative window in selected rows.
- The fix is too conservative: trade count fell from `31` closed trades to `11-19`, and average
  multi-month window return fell to `2.34-3.15%`.
- The no-open-inventory rows are cleaner but economically weak: `2025H1` drops to only `+0.33%`,
  so this does not approach the user's desired month-sized return profile.
- The less strict `7d` basket guard keeps more return but still leaves one open position at
  `-18.95%`, which is not acceptable inventory risk.

### Partial Take-Profit And Trailing Remainder

The next exit-model test added a true partial exit to the portfolio replay:

- sell a configured fraction of the position after the first profit threshold;
- keep the remainder open for a larger target;
- close the remainder if it gives back more than a configured trailing distance from peak;
- stop DCA after a partial exit, so the position becomes a managed winner instead of a new averaging
  candidate.

Selected true-spot results:

| Scenario | Avg Window Return | 2024H2 | 2025H1 | 2025JulNov | Avg Max DD | Closed | Open | Partial exits | Open Unrealized | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd8_spot_baseline_guard_1000` | `3.80%` | `4.67%` | `9.21%` | `-2.49%` | `-5.14%` | `31` | `2` | `0` | `-15.38%` | fail |
| `portfolio_dd8_symbol_30d_partial_trail_1000` | `2.42%` | `4.51%` | `0.49%` | `2.25%` | `-4.49%` | `14` | `0` | `12` | `0.00%` | fail |
| `portfolio_dd8_basket_14d_partial_trail_1000` | `2.39%` | `2.87%` | `0.49%` | `3.82%` | `-3.72%` | `11` | `0` | `10` | `0.00%` | fail |

Interpretation:

- Partial take-profit plus trailing remainder improves the clean no-open-inventory rows slightly:
  `+2.42%` versus `+2.36%` for the comparable strict symbol bear-leg row.
- It does not rescue the return target. The weak `2025H1` window remains around `+0.49%`, which is
  far below the user's desired month-sized return profile.
- Applying partial exits to the looser baseline increased average return to `+4.10%` in the sweep,
  but still left `3` open positions and a negative `2025JulNov`, so it is not a better risk-adjusted
  candidate.
- Exit management helps cash realization, but the core bottleneck is now opportunity quality and
  redeployment, not only how profits are taken.

### Relative-Strength Momentum Rotation

The rotation follow-up tested redeploying capital out of profitable lower-ranked positions and into
top relative-strength symbols. The first strict version required the replacement to also pass the
old drawdown-entry filter; that produced `0` real rotations because strong symbols and dip-entry
symbols rarely overlapped at the same timestamp.

The selected replay therefore uses a separate momentum-redeployment rule:

- sell only profitable positions;
- rank symbols by point-in-time relative strength over `72h` or `168h`;
- exit lower-ranked profitable positions;
- redeploy into top-ranked symbols with positive momentum over the same lookback;
- keep the original spot entry rules for first entries, but allow redeployment candidates to be
  momentum candidates rather than fresh drawdown candidates.

Selected true-spot results:

| Scenario | Avg Window Return | 2024H2 | 2025H1 | 2025JulNov | Avg Max DD | Closed | Open | Partial exits | Rotation exits | Open Unrealized | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `portfolio_dd8_spot_baseline_guard_1000` | `3.80%` | `4.67%` | `9.21%` | `-2.49%` | `-5.14%` | `31` | `2` | `0` | `0` | `-15.38%` | fail |
| `portfolio_dd8_symbol_30d_partial_trail_1000` | `2.42%` | `4.51%` | `0.49%` | `2.25%` | `-4.49%` | `14` | `0` | `12` | `0` | `0.00%` | fail |
| `portfolio_dd8_symbol_30d_momentum_rotation_1000` | `3.46%` | `6.96%` | `1.17%` | `2.25%` | `-5.28%` | `20` | `0` | `16` | `8` | `0.00%` | fail |
| `portfolio_dd8_basket_14d_momentum_rotation_1000` | `2.98%` | `3.23%` | `1.30%` | `4.41%` | `-3.66%` | `18` | `0` | `9` | `8` | `0.00%` | fail |

Interpretation:

- Momentum rotation is the first refinement that materially improves the clean no-open-inventory
  rows: `+3.46%` versus `+2.42%` for the comparable partial/trailing row.
- It also fixes the main structural issue from the stricter rows: more closed trades (`20` versus
  `14`) while keeping open inventory at `0`.
- The balanced basket row has lower drawdown (`-3.66%`) and better `2025JulNov` (`+4.41%`), but
  still weak `2025H1` (`+1.30%`).
- This is directionally promising but not a paper candidate. The returns are still multi-month
  window returns, not the desired month-sized return profile.

## Interpretation

The idea has a real useful part: profitable exits are common. Once a rebound happens, the tested
rules often close with `+3.55%` to `+6.81%` average net return on one-shot closed trades.

The failure is inventory risk. Because the strategy never sells in loss, every symbol/window tends
to leave one unresolved loser. Those open positions average roughly `-32%` to `-33%` unrealized.
That is not "no risk"; it is risk moved from realized loss into capital lockup and portfolio
drawdown.

Confirmed-reversal filters helped but made the sample too sparse. Portfolio DCA helped more: it cut
open unrealized damage from roughly `-32%` to `-13.53%..-17.96%` and produced positive average
window returns.

The market guard is the first clearly useful refinement in the futures-proxy screen. It removed the
negative windows from the best `dd8` variants and materially reduced open inventory:

- `portfolio_dd8_dca_market_guard_1000`: all windows positive, only `1` open position, but average
  window return is still only `5.70%` over multi-month windows;
- `portfolio_dd10_market_guard_aggressive_1000`: higher average return at `7.68%`, all windows
  positive, but still has `2` open positions and only `28` closed trades.

The true spot replay did not confirm the futures-proxy pocket strongly enough. This is not yet close
to the user's monthly-return objective. The improvement is qualitative: portfolio DCA plus
broad-market recovery gating is a better research direction than one-shot dip buying, but the
current rules still buy too early in persistent bear legs. Bear-leg abstention improves risk but
shrinks the opportunity set too far to solve the return target. Partial take-profit plus trailing
remainder is a small improvement on the clean rows but does not change that conclusion. Momentum
rotation improves the clean rows more meaningfully, but still remains below the return objective.

## Decision

Reject the current CT-193 screens as paper candidates.

Do not approve live trading.

Do not claim a working model.

The next CT-193 refinement should keep the `$1000` portfolio cap and improve entry/dca conditions:

- keep broad-market recovery gating;
- use the true spot candles as the default evidence source;
- compare equal-weight basket guard against BTC/ETH-only guard;
- test whether open inventory eventually recovers if windows are extended;
- measure monthly return distribution, not only multi-month window return;
- measure maximum portfolio drawdown and time stuck in open positions, not just closed-trade win
  rate.
- do not continue by only tightening bear-leg abstention thresholds; the selected rows are cleaner
  but too low-return;
- do not continue by only adding nearby partial-take-profit or trailing-stop thresholds;
- do not continue by requiring rotation replacements to also be drawdown candidates; that produced
  no actual rotations;
- next useful branch should broaden the rotation universe or use a higher-frequency redeployment
  cadence, because the selected five-coin universe still provides too little high-quality exposure.
