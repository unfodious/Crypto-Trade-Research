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

## Sample Run

```sh
make sample-meta-strategy
```

The report compares rule-only candidates against ML-filtered candidates and includes rejected-trade analysis. This is research evidence only; live execution remains out of scope.
