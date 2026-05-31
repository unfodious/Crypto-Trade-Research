# CT-201 broad external OI validation

Issue: `CT-201`
Epic: `CT-113`

## Question

CT-200 found a tiny OI-filtered spot-rotation pocket, but it kept only `3` positions. CT-201 tested
whether that pocket survives when the spot universe is expanded from the selected five-symbol set to
the existing broad true-spot universe.

## Data

True spot data was already available from prior CT-194/CT-197 work, so no new downloader path was
needed for this validation pass:

- Universe: `17` Binance spot symbols.
- Symbols: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`,
  `ATOMUSDT`, `XRPUSDT`, `DOTUSDT`, `LINKUSDT`, `NEARUSDT`, `APTUSDT`, `ARBUSDT`, `OPUSDT`,
  `INJUSDT`, `DOGEUSDT`.
- 30m windows:
  - `2024H2`: `150,144` rows, no missing slices.
  - `2025H1`: `147,696` rows, no missing slices.
  - `2025JulNov`: `119,952` rows, no missing slices.
- 15m secondary timeframe:
  - `2024H2`: `300,288` rows, no missing slices.
  - `2025H1`: `295,392` rows, no missing slices.
  - `2025JulNov`: `239,904` rows, no missing slices.

External futures metrics came from CT-178:

- `data/generated/ct178_data_vision_futures_metrics_dataset/clean/futures_metrics.parquet`
- `1,621,961` metric rows.
- `11` futures symbols overlap with the broad spot universe.
- The six spot-only symbols without futures metrics are not included in metrics-matched OI screens.

## Method

Configs:

- `configs/ct201-broad-external-rotation-screen.json`
- `configs/ct201-broad-external-rotation-screen-15m.json`

Commands:

```sh
python -m crypto_trade_research.external_rotation_screen \
  --config configs/ct201-broad-external-rotation-screen.json

python -m crypto_trade_research.external_rotation_screen \
  --config configs/ct201-broad-external-rotation-screen-15m.json
```

The screen regenerates position-level rows from CT-194 broad spot rotation configs, then joins
futures metrics point-in-time by symbol and entry timestamp. Metrics are accepted only if the latest
metrics row is at or before the spot entry and at most `10` minutes old.

Tested screens:

- skip 1h OI expansion greater than `1.5%`;
- skip 1h OI expansion greater than `3.0%`;
- skip 4h OI expansion greater than `5.0%`;
- skip Europe session;
- skip OI expansion or Europe session;
- skip top-trader crowding spread greater than `0.25`;
- skip OI expansion or top-trader crowding.

This is still a selected-position diagnostic. It does not recompute the full portfolio path after a
skipped entry, so it can only justify a later full replay if the selected-position evidence is strong.

## 30m Results

Output:

- `data/generated/ct201_broad_external_rotation_screen/report.json`
- `data/generated/ct201_broad_external_rotation_screen/report.md`

Decision: `reject_external_screen_until_stronger_selected_position_edge`

The broad 30m run produced more entries than CT-200, but no external screen met the evidence gate.

Important rows:

- `portfolio_dd8_broad_spot_baseline_guard_1000`
  - positions: `46`
  - matched metrics: `23`
  - matched baseline avg return: `4.83%`
  - OI/session/crowding filters reduced average return or reduced sample too much.
- `portfolio_dd8_broad_symbol_30d_momentum_rotation_1000`
  - positions: `31`
  - matched metrics: `18`
  - matched baseline avg return: `5.49%`
  - no OI/crowding filter improved enough to matter.
- `portfolio_dd8_broad_basket_14d_momentum_rotation_1000`
  - positions: `29`
  - matched metrics: `17`
  - matched baseline avg return: `2.39%`
  - best diagnostic pockets:
    - skip Europe session: kept `12`, avg return `4.22%`;
    - skip 4h OI expansion > `5%`: kept `12`, avg return `3.90%`;
    - skip 1h OI expansion > `3%`: kept `12`, avg return `3.65%`.

Those basket pockets improved selected-position quality, but kept only `12` positions. That is still
too sparse for full portfolio replay or paper planning.

## 15m Results

Output:

- `data/generated/ct201_broad_external_rotation_screen_15m/report.json`
- `data/generated/ct201_broad_external_rotation_screen_15m/report.md`

Decision: `reject_external_screen_until_stronger_selected_position_edge`

The secondary 15m timeframe did not increase usable sample size. The largest broad baseline had
only `34` positions and `15` metrics-matched positions. Most filtered rows kept between `1` and `12`
positions.

Best-looking 15m improvements were again too sparse:

- `portfolio_dd8_broad_symbol_30d_momentum_rotation_1000` with 1h OI expansion > `3%` skipped:
  kept `5`, avg return `6.96%`;
- same scenario with 4h OI expansion > `5%` skipped: kept `6`, avg return `6.90%`;
- broad baseline with 1h OI expansion > `3%` skipped: kept `12`, avg return `5.55%`.

No row met the minimum evidence threshold.

## Decision

CT-201 is rejected as a paper-trading or full-replay promotion path.

The broader universe answers the CT-200 concern: the prior tiny OI pocket was not merely a
five-symbol artifact, but it also did not scale into enough stable, metrics-matched evidence. The
external OI/session screens can improve some sparse selected-position averages, but they mostly:

- remove already-profitable entries;
- keep too few positions;
- lack enough metrics-matched breadth because only `11` of `17` broad spot symbols have matching
  futures metrics in CT-178;
- remain only selected-position diagnostics, not recomputed portfolio-path evidence.

No live trading, paper runtime, order placement, leverage, or execution behavior was changed.

CT-113 remains open.

## Next Hypothesis

The next branch should stop trying to rescue this OI/session screen with more nearby thresholds.
The better research question is capital efficiency: the spot strategies are often positive but too
slow and sparse to approach the user's monthly-return target. A next issue should test whether
portfolio utilization can be increased without changing the "do not sell at a loss" constraint:

- wider true-spot universe where spot data exists;
- lower drawdown threshold families, but with stricter rebound/failed-breakout guards;
- explicit monthly capital-utilization and idle-cash reporting;
- no live trading changes and no paper promotion unless full-path replay passes.

