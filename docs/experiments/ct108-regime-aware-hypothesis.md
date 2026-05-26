# CT-108 Regime-Aware Hypothesis And Risk Gaps

Date: 2026-05-26

## Scope

CT-108 starts CT-107 after CT-96 produced no promoted paper-trading candidate. The purpose is to
define a new research thesis before any more experiments run.

The next work must change the setup thesis or risk model for a pre-stated reason. It must not widen
the rejected CT-101/CT-102 threshold grids against the same validation/test window.

## Lessons From CT-96

CT-96 showed that several deterministic setup families were structurally negative on the expanded
dataset:

- High-range short fade was negative across all symbols and sessions.
- Complementary long reversal, volume continuation, volatility breakout, and volatility fade
  families were also negative after costs.
- The least-bad candidate, `ct102_volume_long_continuation_h24`, beat rule-only but still had
  negative OOS average R and nearly complete drawdown.
- CT-103 stability gates showed the least-bad candidate lacked positive symbol, session, day, and
  nearby-variant breadth.

These failures suggest the missing piece is not one more nearby entry threshold. The system needs a
reason to abstain when the market regime makes the setup structurally unfavorable.

## Current Feature And Risk Gaps

Current point-in-time features cover price action, participation, simple trend, and volatility
expansion, but the experiment configs do not yet make an explicit regime decision before entry.

Gaps to address:

- No explicit trend-state filter such as above/below moving average with slope agreement.
- No explicit realized-volatility bucket separating normal, compressed, and disorderly candles.
- No market-wide reference regime from BTC/ETH to avoid trading alt setups during broad beta shocks.
- No setup-level abstention rule after adverse recent realized R because backtest position sizing
  keeps taking trades through drawdown.
- No promotion gate that requires a regime slice to be positive before the model can trade inside it.

## Do-Not-Test List

The following are blocked for CT-107 unless a later task first changes the thesis or risk model:

- More `range_position_20` short-fade thresholds around `0.70`, `0.75`, `0.80`, or `0.85`.
- More probability thresholds around `0.50`, `0.55`, or `0.60` for the CT-101 short-fade family.
- More CT-102 12/24-bar variants with the same filters and only tighter/looser constants.
- 48-bar label variants for the same CT-102 families without a pre-stated risk-model reason.
- Any setup filter that depends on labels, future returns, realized PnL, or post-decision highs/lows.

## Proposed Hypotheses

### H1: Trend-Aligned Continuation

High-volume continuation may only be tradable when local trend and market reference trend agree.

Candidate point-in-time filters:

- `volume_zscore_20 >= 1.0`
- `return_1 >= 0.0`
- `ma_slope_20 > 0.0`
- `close >= ma_20`
- optional reference regime: BTC/ETH one-bar or higher-timeframe return not strongly negative

Invalidation:

- OOS average R remains negative after costs.
- Positive expectancy appears in only one symbol, session, or day pocket.
- Drawdown exceeds CT-103 thresholds.

### H2: Volatility Compression Then Expansion

Breakouts may need a compression prerequisite. CT-102 tested expansion alone, which can include
late, disorderly candles after the move has already become costly.

Candidate point-in-time filters:

- current `volatility_expansion_20 >= 1.3`
- prior regime bucket indicates recent compression rather than already-expanded noise
- `close_location >= 0.7` for long breakout or `close_location <= 0.3` for short breakout

Invalidation:

- Compression bucket does not improve OOS expectancy versus rule-only.
- Trade count falls below meaningful aggregate and slice thresholds.

### H3: Risk-Off Abstention

The expanded experiments kept trading through drawdown. A candidate may require a deterministic
research-only abstention rule that blocks trades during unfavorable recent regime states.

Candidate point-in-time filters:

- market-wide BTC/ETH reference return not below a conservative threshold,
- local volatility not in the highest disorderly bucket,
- optional cooldown after a symbol/session has recent adverse realized R in research backtest
  diagnostics, if the cooldown is computed without leaking future labels into features.

Invalidation:

- Abstention improves drawdown only by eliminating too many trades.
- Positive expectancy remains isolated to a lucky day or one symbol.

## Acceptance For CT-109

CT-109 should implement only the smallest deterministic feature/filter layer needed to test these
hypotheses. The first useful additions are likely:

- trend direction from `close` versus `ma_20`,
- trend slope sign from `ma_slope_20`,
- volatility bucket from `volatility_expansion_20`,
- optional reference-market joins only if BTC/ETH rows are available point-in-time.

All new features must respect the existing grouping boundary:

- `venue`
- `market_type`
- `symbol`
- `timeframe`

No feature may read labels or future candles. Generated outputs remain ignored.
