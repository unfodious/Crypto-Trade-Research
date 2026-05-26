# CT-93 Feature, Label, and Setup Iteration Notes

Date: 2026-05-26

Dataset: `data/generated/ct88_real_market_dataset/manifest.json`

Baseline for comparison: CT-91 tested all BTCUSDT/ETHUSDT 1m warm rows with a long 12-bar,
2R target/1R stop label and `return_1` as the decision feature. It rejected the candidate because
the model abstained out of sample and rule-only was negative after costs.

## Guardrails

- Splits remain chronological: train through `2025-07-01T12:00:00Z`, validation through
  `2025-07-01T18:00:00Z`, test through `2025-07-02T00:00:00Z`.
- Features are point-in-time OHLCV features only; labels are generated after the fact and are not
  joined into feature rows.
- Candidate setups are deterministic filters over already available features. The model may only
  estimate `take` or `skip`; it does not own order size, leverage, stops, or execution.
- Promotion thresholds: walk-forward average R >= 0, OOS trades >= 10, max drawdown <= 8%,
  drawdown duration <= 240 bars, leakage/stability/paper-plan gates required.

## Iterations

| Hypothesis | Config | Change | OOS model trades | OOS model avg R | OOS rule avg R | OOS max DD | Decision |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| H1 low-range long pullback | `configs/ct93-pullback-long-range-low.json` | Filter `range_position_20 <= 0.25`; long 12-bar 2R label; decision feature `lower_wick_ratio`. | 27 | -1.1750 | -1.1750 | 27.32% | Reject |
| H2 high-volume long participation | `configs/ct93-volume-long-participation.json` | Filter `volume_zscore_20 >= 1.0`; long 12-bar 2R label; decision feature `volatility_expansion_20`. | 10 | -1.1750 | -1.1750 | 11.15% | Reject |
| H3 high-range short fade, wick filter | `configs/ct93-short-fade-range-high.json` | Filter `range_position_20 >= 0.75`; short 12-bar 2R label; decision feature `upper_wick_ratio`. | 21 | 0.8250 | 0.8573 | 6.85% | Reject |
| H4 high-range short fade, range-position filter | `configs/ct93-short-fade-range-position.json` | Same deterministic short fade setup as H3; decision feature `range_position_20`. | 29 | 0.8940 | 0.8573 | 10.09% | Reject |

## Interpretation

H1 and H2 reject the long continuation/pullback ideas on this one-day futures sample: both model
and rule-only remain negative after costs, and drawdown fails the configured gate.

H3 finds that the deterministic high-range short fade setup is directionally promising, but the
ML wick filter underperforms the rule-only setup out of sample. It is useful research evidence, not
a promoted model.

H4 is the best CT-93 candidate: the ML filter beats rule-only average R out of sample, has enough
trades, and remains positive after costs. It still rejects because max drawdown exceeds the 8% gate
and the current evidence does not include stability checks or a paper-trading plan. Do not promote
it from this one-day window.

## Next Rejection Path

The honest next step is not to relax the test window. Expand the dataset beyond one day, rerun the
high-range short fade setup across multiple sessions, and add stability evidence across symbols,
days, and nearby thresholds. Only if the setup still beats rule-only after costs and passes drawdown
should a separate paper-trading promotion pack be prepared.
