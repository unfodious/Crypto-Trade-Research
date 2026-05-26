# CT-101 Expanded High-Range Short-Fade Matrix

Date: 2026-05-26

## Scope

CT-101 tests the best CT-93 rejection path, `ct93_short_fade_range_position`, on the
CT-96 expanded USD-M futures dataset.

Generated outputs stay under ignored `data/generated/` paths:

- Matrix leaderboard: `data/generated/ct101_short_fade_expanded_matrix/leaderboard.json`
- Matrix Markdown: `data/generated/ct101_short_fade_expanded_matrix/leaderboard.md`
- Segment breakdown for the best aggregate row:
  `data/generated/ct101_short_fade_expanded_matrix/segment_breakdown_rp070_p050.json`

Committed configs:

- Base config: `configs/ct101-short-fade-expanded-base.json`
- Matrix config: `configs/ct101-short-fade-expanded-matrix.json`

## Dataset And Splits

- Dataset: `ct96_expanded_core_futures_dataset`
- Symbols: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`,
  `XRPUSDT`, `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`
- Timeframe: `1m`
- Label: short, 12-bar horizon, 0.4% stop, 0.8% target, `0.0007` cost, `stop_first`
- Train end: `2026-04-25T00:00:00Z`
- Validation end: `2026-05-10T00:00:00Z`
- Test end: `2026-05-25T00:00:00Z`

The matrix varied `range_position_20 >= 0.70, 0.75, 0.80, 0.85` and model probability
thresholds `0.50, 0.55, 0.60`. These are sensitivity evidence, not hidden test-window tuning.

## Leaderboard

All 12 runs completed. All 12 were rejected.

Every row failed the same promotion gates:

- `beats_rule_only_and_naive_oos`
- `walk_forward_metrics_acceptable`
- `drawdown_within_limits`
- `stability_checks_pass`
- `paper_trading_plan_exists`

| Experiment | Model OOS avg R | Rule-only OOS avg R | Trades | Max DD |
| --- | ---: | ---: | ---: | ---: |
| `ct101_short_fade_rp070_p050` | -0.6591 | -0.6726 | 11,642 | 100.00% |
| `ct101_short_fade_rp070_p055` | -0.6611 | -0.6726 | 9,895 | 100.00% |
| `ct101_short_fade_rp070_p060` | -0.6723 | -0.6726 | 8,396 | 100.00% |
| `ct101_short_fade_rp075_p050` | -0.6791 | -0.6767 | 9,891 | 100.00% |
| `ct101_short_fade_rp075_p055` | -0.6821 | -0.6767 | 8,460 | 100.00% |
| `ct101_short_fade_rp075_p060` | -0.6789 | -0.6767 | 6,906 | 100.00% |
| `ct101_short_fade_rp080_p050` | -0.6767 | -0.6736 | 7,953 | 100.00% |
| `ct101_short_fade_rp080_p055` | -0.6799 | -0.6736 | 6,453 | 100.00% |
| `ct101_short_fade_rp080_p060` | -0.6936 | -0.6736 | 4,929 | 100.00% |
| `ct101_short_fade_rp085_p050` | -0.6877 | -0.6850 | 6,015 | 100.00% |
| `ct101_short_fade_rp085_p055` | -0.6982 | -0.6850 | 4,461 | 100.00% |
| `ct101_short_fade_rp085_p060` | -0.7355 | -0.6850 | 3,010 | 100.00% |

The least-bad aggregate row was `ct101_short_fade_rp070_p050`. It slightly beat rule-only
but remained deeply negative and did not beat no-trade.

## Segment Breakdown

The best aggregate row, `ct101_short_fade_rp070_p050`, was negative across all symbols and
coarse UTC sessions.

| Symbol | Model trades | Model avg R |
| --- | ---: | ---: |
| `ADAUSDT` | 714 | -0.9565 |
| `ATOMUSDT` | 1,080 | -0.7028 |
| `AVAXUSDT` | 648 | -0.9481 |
| `BTCUSDT` | 187 | -0.9985 |
| `DOTUSDT` | 1,041 | -0.8119 |
| `ETHUSDT` | 409 | -1.0356 |
| `ICPUSDT` | 2,098 | -0.5344 |
| `SOLUSDT` | 554 | -0.9421 |
| `SUIUSDT` | 1,704 | -0.5905 |
| `TONUSDT` | 2,852 | -0.4197 |
| `XRPUSDT` | 349 | -0.8827 |

| Session | Model trades | Model avg R |
| --- | ---: | ---: |
| Asia UTC 00-07 | 3,724 | -0.7102 |
| Europe UTC 08-15 | 4,104 | -0.6238 |
| US UTC 16-23 | 3,808 | -0.6464 |

Best model days were still negative. The least-bad day was `2026-05-22` with 560 model
trades and `-0.2054` average R. The worst day was `2026-04-25` with 54 model trades and
`-1.1750` average R.

## Decision

Reject the expanded high-range short-fade setup for CT-96 promotion. The CT-93 drawdown
failure was not a one-day artifact; the expanded dataset shows persistent negative OOS
expectancy, 100% max drawdown in the current backtest accounting, and no symbol/session
pocket with positive model expectancy.

CT-102 should test genuinely complementary setups or label variants rather than tightening this
short-fade threshold family against the same test window.
