# CT-114 Multifeature Market-Context Thesis

Date: 2026-05-26

Parent epic: CT-113

## Goal

CT-113 exists because CT-96 and CT-107 rejected simple local 1m setup families. The next research
loop must stop asking whether one local threshold can rescue the strategy and instead train a
model on a richer, explicitly structured view of the market.

The target is a working paper-trading candidate, not another one-off rejection matrix. The epic
should remain open until either a candidate passes promotion gates or the owner explicitly pauses
or rescopes the effort.

## Research Premise

Technical-analysis knowledge should become point-in-time features, setup context, validation rules,
and risk controls. It should not become discretionary hindsight or post-hoc chart reading.

Use the local Crypto Trade skills as the feature source map:

- `crypto-trade-indicators`: trend, momentum, volatility, participation, breadth, failure modes.
- `crypto-trade-market-regime`: top-down regime, BTC/ETH leadership, breadth, risk-on/risk-off.
- `crypto-trade-price-action`: bar pressure, breakout/failure, pullbacks, range position,
  follow-through.
- `crypto-trade-strategy-research`: falsifiable setup, validation, costs, robustness, gates.

## Why CT-107 Failed

CT-107 used useful regime features, but the setup was still narrow:

- local 1m OHLCV only,
- long-only continuation/breakout,
- one decision feature in the baseline model,
- local trend/volatility filters without market-wide beta context,
- fixed stop/target and no adaptive risk state.

The least-bad CT-110 row beat rule-only but remained deeply negative after costs. That means the
next step must change the information set and model class, not only tune thresholds.

## Feature Plan

### Current-Data Feature Pack

These can be built from the existing 1m OHLCV dataset without new exports.

| Group | Features | Purpose | Failure Mode |
| --- | --- | --- | --- |
| Trend | SMA/EMA slopes, MA stack, MACD line/signal/histogram, DMI/ADX | Identify trend direction and strength. | Whipsaw in ranges; lag after reversals. |
| Momentum | RSI, Stoch RSI, stochastic K/D, ROC windows, momentum divergence proxies | Measure speed, pullback reset, exhaustion. | Overbought/oversold persists in strong trends. |
| Volatility | ATR, normalized ATR, Bollinger width/position, squeeze/expansion, realized vol buckets | Normalize stops, detect compression/expansion. | Expansion can be late or disorderly. |
| Participation | Relative volume, volume z-score, volume trend, close-location volume pressure | Confirm or warn on moves. | Venue volume can distort signal quality. |
| Price Action | Body/wick pressure, close location, overlap, consecutive trend bars, range position, distance from local highs/lows | Encode bar-by-bar auction behavior. | Candle patterns are weak without context. |
| Relative Behavior | Per-symbol rolling rank, return percentile, volatility percentile within universe snapshot | Identify leaders/laggards. | Current tracked universe can create selection bias. |

Implementation rule: add broad windows with pre-declared horizons rather than optimized single
settings. Prefer `3/5/8/13/20/34/55` or similar horizon families where needed, but treat highly
correlated duplicates as model input risk.

### New Context Feature Pack

These need cross-symbol joins, multi-timeframe exports, or both.

| Group | Features | Purpose | Data Requirement |
| --- | --- | --- | --- |
| BTC/ETH Reference | BTC/ETH trend regime, recent shock, volatility bucket, MA slope, range position | Avoid alt signals during unstable market beta. | BTC/ETH 1m rows already present; joins must be point-in-time. |
| Market Breadth | Percent of tracked symbols above MA, positive return breadth, breadth thrust/failure | Detect broad risk-on/risk-off participation. | Same timestamp universe snapshot. |
| Correlation/Beta | Rolling beta/correlation to BTC/ETH, relative strength versus BTC/ETH | Prefer leaders in risk-on, avoid beta shock victims. | Rolling historical returns only. |
| Multi-Timeframe | 5m/15m/1h trend, volatility, RSI/ADX, support/resistance context | Align higher/base/lower timeframe stack. | Safe resampling from 1m or explicit higher-timeframe export. |
| Perp Context | Funding, basis, open interest, liquidation pressure | Capture crowding and forced flow. | Not in current dataset; requires separate safe data source. |

For CT-113, BTC/ETH reference and breadth should be first because the current dataset already
contains BTCUSDT and ETHUSDT 1m candles. Funding/open-interest is valuable but should be a later
data-ingestion task unless already available in a trusted export.

## Model Plan

The CT-110 baseline used one decision feature. CT-113 needs multifeature baselines before complex
models.

Minimum model stack:

1. `no_trade`: zero-risk baseline.
2. `rule_only`: deterministic setup without model filtering.
3. `single_feature`: current linear threshold model for comparison.
4. `logistic_ridge`: multifeature classifier with regularization.
5. `expected_r_ridge`: multifeature expected-R regression or ranking baseline.
6. Optional tree/boosting model only after the linear baselines work and can be validated without
   dependency or reproducibility churn.

Validation rules:

- Chronological train/validation/test only.
- Calibrate probability thresholds on validation, never on test.
- Report feature importance or coefficients, plus permutation checks where feasible.
- Compare performance by symbol, session, day, regime, and nearby parameter families.
- Reject models that improve headline metrics by eliminating nearly all trades unless ranking or
  capital allocation explicitly requires sparse trade selection.

## Objective Plan

The target should not be only `target_before_stop`.

Add objective variants:

- target-before-stop probability,
- expected R after costs,
- stop-first probability,
- top-N setup ranking per time bucket,
- volatility-adjusted stop/target variants,
- side-specific long and short objectives.

Working candidate definition:

- positive OOS expected R after costs,
- beats `no_trade`, `rule_only`, and `single_feature`,
- drawdown within gate,
- enough OOS trades for the intended cadence,
- stable across symbols/sessions/days/regimes,
- paper-trading plan can be attached without inventing missing evidence.

## Risk Model Plan

CT-107 showed that drawdown is the binding blocker. CT-113 must treat risk state as a first-class
research object.

Controls to test:

- cooldown after prior realized losses, computed only from completed historical trades,
- max trades per symbol/session,
- portfolio exposure cap across correlated symbols,
- volatility-aware no-trade states,
- side-specific gates,
- BTC/ETH shock abstention,
- ranking top-N candidates instead of trading every qualifying setup.

Risk-model reporting must separate:

- entry/model edge before risk controls,
- risk-control effect on expectancy,
- risk-control effect on drawdown,
- trade count and concentration changes.

## Anti-Overfit Rules

This epic is allowed to enrich data aggressively, but not to chase arbitrary backtest wins.

Hard rules:

- No labels, future highs/lows, future returns, or post-decision PnL in features.
- No test-period threshold tuning.
- No promotion from one lucky symbol, session, day, or parameter value.
- No paper-trading pack for rejected candidates.
- Generated private data and model artifacts stay under ignored paths.
- Every feature family must state its market question and failure mode.

## Task Sequence

1. CT-115: implement technical indicator and price-action feature library.
2. CT-116: add BTC/ETH reference, breadth, correlation/beta, and multi-timeframe context.
3. CT-117: implement multifeature baseline runner and artifact/report support.
4. CT-118: add risk-model and objective experiments.
5. CT-119: run controlled multifeature matrices and gates.

If CT-119 rejects, CT-113 remains open and the next task must change the thesis or data source
before another matrix.
