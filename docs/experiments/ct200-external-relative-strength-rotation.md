# CT-200 external relative-strength rotation screen

Issue: `CT-200`
Epic: `CT-113`

## Question

CT-199 showed that loosening paper-trading gates was not justified: skipped paper signals were
negative on average. CT-200 tested a different branch of the CT-113 search: keep the spot
drawdown/relative-strength rotation family, but use external futures context as an entry screen.

The tested context uses historical Binance Data Vision futures metrics from CT-178:

- same-symbol open-interest notional change over 1h;
- Europe/Asia/US session flags;
- top-trader long/short crowding versus the global long/short ratio.

Order-book walls, liquidation heatmaps, and whale/OI live feeds remain forward-only evidence in
this repository. They are not available as long historical point-in-time features here, so they were
not used in this historical replay screen.

## Method

Config:

- `configs/ct200-external-rotation-selected-screen.json`

Runner:

```sh
python -m crypto_trade_research.external_rotation_screen \
  --config configs/ct200-external-rotation-selected-screen.json
```

Output:

- `data/generated/ct200_external_rotation_selected_screen/report.json`
- `data/generated/ct200_external_rotation_selected_screen/report.md`

The screen regenerates selected position rows from the CT-193 30m no-lookahead spot rotation
config, then joins futures metrics point-in-time by symbol and entry timestamp. The join only uses
the last metrics row at or before the spot entry time, with a maximum metrics age of 10 minutes.

Important limitation: this is a selected-position diagnostic, not a full portfolio replay. If an entry
is skipped, the report does not recompute later cash availability, open-position contention, DCA
state, or downstream rotation paths. A positive screen is only permission to build a full replay.

## Results

### `portfolio_dd8_spot_baseline_guard_1000`

- Positions: `25`
- Matched futures metrics positions: `20`
- Matched baseline avg return: `5.80%`
- Matched baseline win rate: `100.00%`
- Matched baseline profit factor: `inf`

External filters did not create a useful improvement. Most filters reduced trade count sharply while
removing already-profitable entries. The Europe-session filter increased average return to `7.33%`,
but only kept `6` positions.

### `portfolio_dd8_symbol_30d_momentum_rotation_1000`

- Positions: `11`
- Matched futures metrics positions: `9`
- Matched baseline avg return: `4.73%`
- Matched baseline win rate: `100.00%`
- Matched baseline profit factor: `inf`

No external rule improved the selected-position evidence. OI/session filters mainly reduced sample
size and total PnL.

### `portfolio_dd8_basket_14d_momentum_rotation_1000`

- Positions: `14`
- Matched futures metrics positions: `8`
- Matched baseline avg return: `2.23%`
- Matched baseline win rate: `87.50%`
- Matched baseline profit factor: `2.1326`

The only interesting diagnostic pocket was:

- Rule: `skip_oi_expansion_1h_gt_1p5`
- Kept positions: `3`
- Avg return: `5.65%`
- Win rate: `100.00%`
- Profit factor: `inf`
- Window breadth: `100.00%`
- Symbol breadth: `100.00%`

This is too sparse to promote. It is a note for a broader-data hypothesis, not a candidate.

## Decision

CT-200 is rejected as a paper-trading candidate.

Reasons:

- no rule met the minimum selected-position evidence threshold;
- the only improved OI pocket kept `3` positions, which is not enough for a stable candidate;
- the strongest existing spot rows already have very small trade counts;
- the diagnostic does not recompute full portfolio path after skipped entries;
- no live or paper-trading runtime behavior was changed.

CT-113 remains open.

## Next Hypothesis

The next research step should not tune the same tiny five-symbol sample harder. The useful path is
to expand the true-spot historical universe and rerun spot drawdown/rotation with external OI
features on more symbols and more eligible entries. The goal is to learn whether the tiny basket OI
pocket survives when the sample is no longer sparse.

