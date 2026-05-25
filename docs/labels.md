# Labeling

Labels are after-the-fact targets for supervised learning and strategy evaluation. They may use future market data; feature generation must not.

## Current Labels

- `forward_return`: side-adjusted return over the configured future horizon.
- `directional_class`: `up`, `down`, `flat`, or `no_trade` after costs/noise threshold.
- `target_before_stop`: whether the configured target was reached before the stop.
- `realized_r_after_costs`: R multiple after fees/slippage proxy.
- `max_favorable_excursion_r`: best favorable future move in R.
- `max_adverse_excursion_r`: worst adverse future move in R.
- `time_to_target_bars`: bars until target hit.
- `time_to_stop_bars`: bars until stop hit.
- `no_trade_reason`: explicit reason a row should be neutral or excluded.

## Configuration

Every label run must define:

- `horizon_bars`
- `side`
- `stop_loss_pct`
- `target_pct`
- `cost_pct`
- `flat_threshold_pct`

This makes the 1R definition explicit: entry is the decision candle close, stop and target are percentage models, and cost is converted to R by dividing by stop distance.

## Separation Rule

Label rows include `availability=after_the_fact` in the manifest. They belong in separate label datasets and should never be read by feature builders. Join labels to features only by stable keys:

- venue
- market type
- symbol
- timeframe
- decision time

## Sample Run

```sh
make sample-labels
```

This writes ignored files under `data/generated/sample_labels/`.
