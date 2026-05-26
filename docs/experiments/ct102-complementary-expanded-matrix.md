# CT-102 Complementary Expanded Setup Matrix

Date: 2026-05-26

## Scope

CT-102 tests complementary deterministic setup families on the CT-96 expanded USD-M futures
dataset, rather than continuing to tighten the CT-101 high-range short-fade family.

Generated outputs stay under ignored `data/generated/` paths:

- Matrix leaderboard: `data/generated/ct102_complementary_expanded_matrix/leaderboard.json`
- Matrix Markdown: `data/generated/ct102_complementary_expanded_matrix/leaderboard.md`
- Segment breakdown for the least-bad row:
  `data/generated/ct102_complementary_expanded_matrix/segment_breakdown_volume_long_h24.json`

Committed configs:

- `configs/ct102-long-reversal-expanded-base.json`
- `configs/ct102-volume-continuation-expanded-base.json`
- `configs/ct102-volatility-breakout-expanded-base.json`
- `configs/ct102-volatility-fade-expanded-base.json`
- `configs/ct102-complementary-expanded-matrix.json`

## Dataset And Splits

- Dataset: `ct96_expanded_core_futures_dataset`
- Symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`,
  `XRPUSDT`, `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`
- Timeframe: `1m`
- Train end: `2026-04-25T00:00:00Z`
- Validation end: `2026-05-10T00:00:00Z`
- Test end: `2026-05-25T00:00:00Z`
- Cost assumptions: 4 bps fee, 2 bps slippage, 0 bps funding, no optimistic cost removal
- Tie breaker: `stop_first`

The matrix uses deterministic point-in-time feature filters only. Labels are generated separately
after the fact and are not used as setup filters.

## Candidate Families

| Family | Side | Setup filter | Decision feature | Horizons |
| --- | --- | --- | --- | --- |
| Range-low long reversal | Long | `range_position_20 <= 0.25` and `lower_wick_ratio >= 0.20` | `lower_wick_ratio` | 12, 24 |
| High-volume continuation | Long | `volume_zscore_20 >= 1.0` and `return_1 >= 0.0` | `volatility_expansion_20` | 12, 24 |
| Volatility breakout | Long | `volatility_expansion_20 >= 1.5` and `close_location >= 0.70` | `close_location` | 12, 24 |
| Volatility upper-wick fade | Short | `volatility_expansion_20 >= 1.5` and `upper_wick_ratio >= 0.35` | `upper_wick_ratio` | 12, 24 |

## Leaderboard

All 8 runs completed. All 8 were rejected.

Every row failed the same promotion gates:

- `beats_rule_only_and_naive_oos`
- `walk_forward_metrics_acceptable`
- `drawdown_within_limits`
- `stability_checks_pass`
- `paper_trading_plan_exists`

| Experiment | Model OOS avg R | Rule-only OOS avg R | Trades | Max DD |
| --- | ---: | ---: | ---: | ---: |
| `ct102_long_reversal_low_h12` | -0.6963 | -0.7393 | 5,415 | 100.00% |
| `ct102_long_reversal_low_h24` | -0.5855 | -0.6235 | 8,779 | 100.00% |
| `ct102_volume_long_continuation_h12` | -0.4951 | -0.5795 | 1,509 | 99.97% |
| `ct102_volume_long_continuation_h24` | -0.4576 | -0.5360 | 2,965 | 100.00% |
| `ct102_volatility_breakout_long_h12` | -0.6199 | -0.6361 | 1,616 | 100.00% |
| `ct102_volatility_breakout_long_h24` | -0.5357 | -0.5733 | 2,656 | 100.00% |
| `ct102_volatility_fade_short_h12` | -0.6588 | -0.6967 | 1,110 | 99.94% |
| `ct102_volatility_fade_short_h24` | -0.5879 | -0.6176 | 1,855 | 100.00% |

The least-bad aggregate row was `ct102_volume_long_continuation_h24`. It beat rule-only but
remained deeply negative and did not beat no-trade.

## Segment Breakdown

For `ct102_volume_long_continuation_h24`, model expectancy was negative across all symbols and
all coarse UTC sessions.

| Symbol | Model trades | Model avg R |
| --- | ---: | ---: |
| `ADAUSDT` | 180 | -0.5583 |
| `ATOMUSDT` | 325 | -0.4827 |
| `AVAXUSDT` | 210 | -0.6036 |
| `BTCUSDT` | 97 | -0.4946 |
| `DOTUSDT` | 201 | -0.4138 |
| `ETHUSDT` | 160 | -0.4625 |
| `ICPUSDT` | 445 | -0.5413 |
| `SOLUSDT` | 203 | -0.5248 |
| `SUIUSDT` | 391 | -0.2773 |
| `TONUSDT` | 611 | -0.3550 |
| `XRPUSDT` | 142 | -0.6680 |

| Session | Model trades | Model avg R |
| --- | ---: | ---: |
| Asia UTC 00-07 | 893 | -0.5535 |
| Europe UTC 08-15 | 1,062 | -0.4914 |
| US UTC 16-23 | 1,010 | -0.3374 |

The best model day was `2026-05-23` with 144 trades and `0.5125` average R, but that was a
single-day pocket inside an otherwise negative OOS profile. The worst day was `2026-04-25` with
36 trades and `-1.1750` average R.

## Decision

Reject all CT-102 complementary setup families for CT-96 promotion. The 24-bar variants were
less negative than their 12-bar counterparts and often beat rule-only, but none produced positive
OOS expectancy, acceptable drawdown, or broad symbol/session support.

Do not expand these families to 48-bar labels for promotion evidence unless a separate research
task first changes the risk model or setup definition for a reason that does not depend on this
test-window outcome.
