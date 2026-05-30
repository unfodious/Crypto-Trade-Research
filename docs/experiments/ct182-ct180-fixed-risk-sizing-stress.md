# CT-182 CT-180 Fixed-Risk Sizing Stress

Status: research-only sizing stress; no live approval.

CT-181 prepared the CT-180 OI/Europe shadow paper pack using the existing paper sizing semantics.
The user correctly noted that the resulting dollar PnL on a `$1,000` account is small because the
historical backtest uses `risk_per_trade_pct * confidence`, so effective risk can be far below `1%`.

CT-182 asks a counterfactual question:

> What would the same CT-180 historical accepted trades look like if each accepted trade used fixed
> risk of `0.25%`, `0.50%`, or `1.00%` of current equity?

This does not change the paper pack and does not approve live trading.

## Method

Input:

- `data/generated/ct180_2024h2_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025h1_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025julnov_oi_high_or_europe_replay/replay_report.json`

The report reads each window's `accepted_trades.parquet`, sorts trades by decision time, and
compounds from `$1,000` using:

```text
pnl = current_equity * fixed_risk_per_trade_pct * net_r
```

Configs and generated outputs:

- `configs/ct182-ct180-fixed-risk-sizing-stress.json`
- `data/generated/ct182_ct180_fixed_risk_sizing_stress/report.json`
- `data/generated/ct182_ct180_fixed_risk_sizing_stress/report.md`

## Summary

| Fixed risk per trade | Final equity | Total PnL | Return | Max DD | Worst month |
| ---: | ---: | ---: | ---: | ---: | --- |
| `0.25%` | `$1,513.54` | `$513.54` | `51.35%` | `15.91%` | `2025-03`, `-7.22%` |
| `0.50%` | `$2,246.96` | `$1,246.96` | `124.70%` | `29.52%` | `2025-03`, `-14.14%` |
| `1.00%` | `$4,674.23` | `$3,674.23` | `367.42%` | `50.96%` | `2025-03`, `-27.07%` |

The fixed-risk sizing confirms that CT-180's historical edge can produce meaningful account-level
returns, but it also exposes the cost of that leverage: drawdown rises quickly.

## Monthly Result At 0.25% Fixed Risk

This is the least aggressive tested fixed-risk setting.

| Month | Trades | PnL | Return | End equity | Avg R |
| --- | ---: | ---: | ---: | ---: | ---: |
| `2024-07` | `71` | `$69.49` | `6.95%` | `$1,069.49` | `0.3800` |
| `2024-08` | `207` | `$61.07` | `5.71%` | `$1,130.56` | `0.1090` |
| `2024-09` | `196` | `$4.98` | `0.44%` | `$1,135.54` | `0.0103` |
| `2024-10` | `95` | `$67.83` | `5.97%` | `$1,203.36` | `0.2461` |
| `2024-11` | `11` | `$-2.59` | `-0.22%` | `$1,200.77` | `-0.0764` |
| `2024-12` | `63` | `$6.57` | `0.55%` | `$1,207.34` | `0.0362` |
| `2025-01` | `121` | `$114.54` | `9.49%` | `$1,321.87` | `0.3020` |
| `2025-02` | `273` | `$65.13` | `4.93%` | `$1,387.00` | `0.0724` |
| `2025-03` | `364` | `$-100.12` | `-7.22%` | `$1,286.88` | `-0.0809` |
| `2025-04` | `216` | `$57.65` | `4.48%` | `$1,344.53` | `0.0825` |
| `2025-05` | `133` | `$-29.32` | `-2.18%` | `$1,315.22` | `-0.0657` |
| `2025-06` | `143` | `$95.92` | `7.29%` | `$1,411.14` | `0.1978` |
| `2025-08` | `40` | `$30.58` | `2.17%` | `$1,441.72` | `0.2156` |
| `2025-09` | `32` | `$11.01` | `0.76%` | `$1,452.73` | `0.0960` |
| `2025-10` | `380` | `$-8.97` | `-0.62%` | `$1,443.76` | `-0.0051` |
| `2025-11` | `191` | `$69.79` | `4.83%` | `$1,513.54` | `0.1010` |

## Interpretation

`0.25%` fixed risk is the only tested scenario that looks remotely compatible with cautious paper
evaluation, but it still breaches the existing `8%` drawdown gate with `15.91%` max historical DD.

`0.50%` and `1.00%` fixed risk are not acceptable working-model sizing candidates under the current
gate. They produce attractive historical returns, but the drawdowns are too large for a first
paper-to-live discussion.

The main lesson is not "use more leverage." The lesson is:

- the CT-180 signal has enough historical edge that sizing matters;
- the current confidence-scaled sizing is too conservative for account-level growth;
- naive fixed-risk scaling is too aggressive for the existing drawdown gate;
- a next useful research step is adaptive sizing/risk throttling, not immediate live sizing.

## Decision

Do not change CT-181 paper/shadow pack sizing yet.

Do not approve live trading.

Keep CT-113 open.

Recommended next hypothesis: test capped/adaptive fixed-risk sizing, for example:

- start at `0.10%` to `0.25%` risk per trade;
- reduce risk after losing streaks or monthly drawdown;
- cap concurrent portfolio risk;
- pause after monthly loss limits;
- require the same CT-180 abstention filters.
