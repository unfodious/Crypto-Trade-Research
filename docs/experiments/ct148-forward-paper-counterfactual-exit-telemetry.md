# CT-148 Forward-Paper Counterfactual Exit Telemetry

Date: 2026-05-27

Issue: CT-148

Epic: CT-113

## Decision

Added observation-only counterfactual exit telemetry to the forward-paper runner and monitoring
report. This does not change CT-145 entries, fixed exits, paper fills, live approval state, or any
runtime trading behavior.

## Motivation

CT-147 showed that the favorable-then-fail pattern is real in historical selected trades, but
dynamic breakeven/trailing exits did not beat the fixed CT-145 candidate after costs and stability
gates. The useful next step is to observe whether the same pattern appears in fresh forward-paper
evidence without changing the paper candidate mid-stream.

## Added Ledger Fields

Closed forward-paper trades now include:

- `max_favorable_excursion_r`
- `max_adverse_excursion_r`
- `reached_0_5r`
- `reached_1_0r`
- `reached_1_5r`
- `reached_2_0r`
- `counterfactual_exits`

`counterfactual_exits` currently reports:

- `breakeven_after_1r`
- `breakeven_lock_0_1r_after_1r`
- `breakeven_lock_0_1r_trail_1_5r_after_1r`

Each counterfactual reports `exit_reason`, `bars_held`, `net_r`, `gross_r`, and
`time_to_breakeven_bars`.

## Added Monitoring Metrics

The paper monitoring report now aggregates:

- `reached_0_5r_count`
- `reached_1_0r_count`
- `reached_1_5r_count`
- `reached_2_0r_count`
- `reached_0_5r_then_lost_count`
- `reached_1_0r_then_lost_count`
- `reached_1_5r_then_lost_count`
- `counterfactual_exit_metrics`

These metrics help answer whether fresh paper trades often move favorably before closing negative.

## Safety Boundary

Research-only:

- no live credentials;
- no live order placement or cancellation;
- no leverage or margin changes;
- no runtime trade-state writes;
- no change to CT-145 fixed paper exit behavior;
- `live_trading_approved` and `working_model` remain `false`.
