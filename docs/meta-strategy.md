# Meta-Strategy

The first practical ML strategy is a meta-strategy, not an autonomous buy/sell/hold agent.

## Flow

1. Deterministic setup rules generate candidate trades.
2. ML estimates setup quality: target-before-stop probability, expected R, stopout/adverse-excursion risk, optional regime probability.
3. Deterministic gates decide take or skip.
4. Size remains rule-based through fixed risk and exposure caps.

## Current Setup

The first deterministic setup is `trend_pullback_continuation`:

- price above moving average
- positive moving-average slope
- one-bar pullback
- close not too high in the rolling range

## Gates

- probability must clear validation-selected threshold
- expected R must clear threshold after costs/noise
- stopout risk must be below the configured cap
- symbol exposure must remain below the cap

When candidate setups include `exit_time`, symbol exposure is duration-aware: risk is released once
the candidate exit time is at or before the next decision time. Candidates without `exit_time` remain
active for the whole evaluation window.

## Sample Run

```sh
make sample-meta-strategy
```

The report compares rule-only candidates against ML-filtered candidates and includes rejected-trade analysis. This is research evidence only; live execution remains out of scope.
