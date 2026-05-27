# CT-176 Selected-Trade Abstention Sensitivity

Status: rejected; no live approval.

CT-175 rejected the strict ETH-led deleveraging abstention rule, but also exposed an iteration cost:
full historical replay is too slow for screening many nearby abstention patterns. CT-176 adds a
fast selected-trade sensitivity harness and uses it to test broader predeclared weakness filters
before spending more full replay time.

## Implementation

Added `crypto_trade_research.selected_trade_abstention` and the CLI entrypoint
`crypto-trade-build-selected-trade-abstention`.

The harness:

- reads cached base `selected_trades.parquet` from historical replay outputs;
- joins only required point-in-time feature columns from cached feature parquet via Polars;
- applies each abstention rule before backtest risk controls;
- recomputes `evaluate_signal_strategy` metrics using the frozen pack risk controls;
- writes JSON and Markdown reports under ignored `data/generated/`.

This is a research-only screen. It does not rescore models, regenerate labels, or approve a
candidate. Any promising rule still requires full replay before promotion.

Config:

- `configs/ct176-selected-trade-abstention-matrix.json`.

Output:

- `data/generated/ct176_selected_trade_abstention_matrix/report.json`;
- `data/generated/ct176_selected_trade_abstention_matrix/report.md`.

## Matrix

Windows:

- H2 2024: CT-174 base replay;
- H1 2025: CT-172 base replay;
- Jul-Nov 2025: CT-169 base replay.

Rules:

- `ct175_strict_eth_deleveraging`;
- `eth_15m_down_breadth_weak`;
- `eth_15m_trend_down_breadth_weak`;
- `btc_eth_15m_down_breadth_weak`;
- `riskon_15m_weak`;
- `breadth_15m_weak`;
- `eth_5m15m_down_riskon_weak`.

## Results

Best non-base rules by H1 2025 result:

| Candidate | Rule | H1 skipped selected rows | H1 trades | H1 Avg R | H1 Max DD | H1 PF | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| CT-145 no-TON | `ct175_strict_eth_deleveraging` | 18 | 2,241 | -0.0010 | 9.85% | 0.9981 | reject |
| CT-145 no-TON | `eth_5m15m_down_riskon_weak` | 94 | 2,223 | -0.0074 | 10.00% | 0.9866 | reject |
| CT-145 no-TON | `eth_15m_trend_down_breadth_weak` | 891 | 2,030 | -0.0200 | 10.10% | 0.9633 | reject |
| CT-156 high-beta+DOT | `eth_5m15m_down_riskon_weak` | 41 | 1,078 | -0.0217 | 11.44% | 0.9652 | reject |
| CT-156 high-beta+DOT | `eth_15m_down_breadth_weak` | 1,018 | 626 | -0.0326 | 8.22% | 0.9511 | reject |
| CT-156 high-beta+DOT | `ct175_strict_eth_deleveraging` | 15 | 1,083 | -0.0357 | 11.18% | 0.9431 | reject |

Cross-window highlights:

| Window | Candidate | Best rule by Avg R | Trades | Avg R | Max DD | PF |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| H2 2024 | CT-145 no-TON | `eth_15m_trend_down_breadth_weak` / `riskon_15m_weak` | 1,359 / 1,352 | 0.1458 | 4.65% / 3.61% | 1.2987 / 1.3054 |
| H2 2024 | CT-156 high-beta+DOT | `breadth_15m_weak` | 382 | 0.0521 | 6.98% | 1.0831 |
| H1 2025 | CT-145 no-TON | `ct175_strict_eth_deleveraging` | 2,241 | -0.0010 | 9.85% | 0.9981 |
| H1 2025 | CT-156 high-beta+DOT | `eth_5m15m_down_riskon_weak` | 1,078 | -0.0217 | 11.44% | 0.9652 |
| Jul-Nov 2025 | CT-145 no-TON | `riskon_15m_weak` | 981 | 0.0435 | 7.99% | 1.0883 |
| Jul-Nov 2025 | CT-156 high-beta+DOT | `eth_5m15m_down_riskon_weak` | 659 | 0.0765 | 9.19% | 1.1327 |

The recomputed base metrics matched the historical replay reports, so the harness is consistent
with the existing backtest path for selected trades.

## Interpretation

Broader OHLCV-derived weakness filters do not rescue the Jan-Jun 2025 failure. The stricter CT-175
rule gets CT-145 close to flat but skips too little exposure to be useful. Broader ETH/BTC/breadth
rules skip hundreds to more than a thousand selected rows, but they generally make H1 2025 worse
and often damage positive windows.

This suggests the failure is not a simple "avoid down ETH/BTC/breadth bars" problem. The CT-145 and
CT-156 edge appears to depend on a more specific positioning or crowding context that is not
separable with the current OHLCV/funding/market-breadth features.

## Decision

No working model claim.

No paper-to-live promotion.

Keep CT-113 open.

Keep CT-145 and CT-156 forward-paper streams observation-only.

## Next Step

Create the next CT-113 hypothesis around genuinely external futures positioning/crowding evidence
instead of more OHLCV-derived abstention thresholds. Candidate direction: use the existing forward
external streams and research whether comparable historical archives are available for open
interest, liquidation clusters, order-book imbalance, or top-trader long/short positioning.
