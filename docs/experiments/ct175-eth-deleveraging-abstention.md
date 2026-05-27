# CT-175 ETH-Led Deleveraging Abstention

Status: rejected; no live approval.

CT-174 showed that a simple Europe-session abstention rule did not validate on fresh H2 2024 data.
CT-175 tests a stricter point-in-time ETH-led weakness rule against the same frozen CT-145 and
CT-156 paper-pack candidates. The goal is to see whether the Jan-Jun 2025 failure can be avoided
without retraining, threshold retuning, symbol re-selection, or changing live trading behavior.

## Predeclared Hypothesis

Skip a selected long trade when all of these point-in-time conditions are true:

- `eth_trend_above_ma_20 <= 0`;
- `mtf_5m_eth_trend_above_ma_20 <= 0`;
- `mtf_15m_eth_trend_above_ma_20 <= 0`;
- `mtf_15m_eth_return_1 < 0`;
- `mtf_15m_market_positive_return_fraction < 0.5`.

This represents persistent ETH weakness across 1m/5m/15m plus weak market breadth. The rule is
applied after frozen pack selection and before label generation/backtest risk controls.

## Implementation

Added optional research-only `abstention_filters` to `historical_holdout_replay`. The filter is an
AND pattern: if every configured feature condition passes, the selected row is removed before
labels and before the backtest risk-control layer.

Configs:

- `configs/ct175-2024h2-eth-deleveraging-abstention-replay.json`;
- `configs/ct175-2025h1-eth-deleveraging-abstention-replay.json`;
- `configs/ct175-2025julnov-eth-deleveraging-abstention-replay.json`.

All runs use frozen CT-145/CT-156 pack manifests and existing feature caches from CT-174, CT-172,
and CT-169.

## Results

| Window | Candidate | Run | Skipped selected rows | Trades | Avg R | Max DD | Profit factor | Decision |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| H2 2024 | CT-145 no-TON | base | 0 | 1,511 | 0.1455 | 3.74% | 1.3029 | diagnostic pass |
| H2 2024 | CT-145 no-TON | ETH abstention | 10 | 1,505 | 0.1433 | 3.75% | 1.2976 | no improvement |
| H2 2024 | CT-156 high-beta+DOT | base | 0 | 654 | 0.0286 | 8.21% | 1.0481 | reject: DD |
| H2 2024 | CT-156 high-beta+DOT | ETH abstention | 5 | 653 | 0.0379 | 8.10% | 1.0637 | still reject: DD |
| H1 2025 | CT-145 no-TON | base | 0 | 2,242 | -0.0083 | 9.85% | 0.9849 | reject |
| H1 2025 | CT-145 no-TON | ETH abstention | 18 | 2,241 | -0.0010 | 9.85% | 0.9981 | reject |
| H1 2025 | CT-156 high-beta+DOT | base | 0 | 1,096 | -0.0215 | 11.17% | 0.9654 | reject |
| H1 2025 | CT-156 high-beta+DOT | ETH abstention | 15 | 1,083 | -0.0357 | 11.18% | 0.9431 | worse |
| Jul-Nov 2025 | CT-145 no-TON | base | 0 | 1,255 | 0.0287 | 4.34% | 1.0558 | diagnostic pass |
| Jul-Nov 2025 | CT-145 no-TON | ETH abstention | 13 | 1,252 | 0.0374 | 4.34% | 1.0732 | marginal improvement |
| Jul-Nov 2025 | CT-156 high-beta+DOT | base | 0 | 672 | 0.0716 | 8.32% | 1.1248 | reject: DD |
| Jul-Nov 2025 | CT-156 high-beta+DOT | ETH abstention | 7 | 669 | 0.0762 | 8.34% | 1.1334 | still reject: DD |

## Interpretation

The strict ETH-led deleveraging rule does not materially change exposure. It removes only `5` to
`18` selected rows per run out of thousands of selected rows, so it cannot explain or repair the
H1 2025 failure.

CT-145 nearly reaches break-even on H1 2025 after abstention, but it is still negative after costs
and keeps the same `9.85%` max drawdown. CT-156 gets worse on the key H1 2025 holdout and continues
to fail the drawdown gate in the other windows.

This does not prove ETH/BTC weakness is irrelevant. It only rejects this strict point-in-time
definition. A broader weakness/risk-off abstention matrix might still be worth testing, but it
should be screened with a faster selected-trade sensitivity harness before more full replay runs.

## Decision

No working model claim.

No paper-to-live promotion.

Keep CT-113 open.

Keep CT-145 and CT-156 forward-paper streams observation-only.

## Next Step

Created CT-176 to add a selected-trade abstention sensitivity harness and test broader predeclared
weakness patterns across H2 2024, H1 2025, and Jul-Nov 2025. Only patterns that survive that cheap
screen should be promoted to full historical replay.
