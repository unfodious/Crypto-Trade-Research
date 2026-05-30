# CT-186 High-Return Monthly Target

Status: rejected; research-only evidence.

CT-186 answers a direct follow-up question after CT-184/CT-185: can the current CT-180/CT-184
trade stream be tuned toward roughly `30%` monthly returns, instead of roughly `35-42%` over the
full historical replay period?

## Method

Input replay reports:

- `data/generated/ct180_2024h2_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025h1_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025julnov_oi_high_or_europe_replay/replay_report.json`

Config and generated report:

- `configs/ct186-high-return-monthly-target.json`
- `data/generated/ct186_high_return_monthly_target/report.json`
- `data/generated/ct186_high_return_monthly_target/report.md`

The report rebuilds the accepted trade stream from replay `selected_trades.parquet`, applies the
frozen pack risk controls, then simulates account sizing from `$1,000`. It tests:

- CT-184/core-4 and CT-183/core-3 symbol sets;
- risk per accepted trade from `0.25%` up to `5%`;
- rank-1-only, probability `>= 0.60`, and positive expected-R subsets.

Target gate:

- geometric average monthly return `>= 30%`;
- max drawdown `<= 8%`;
- at least `100` accepted trades;
- positive reset-window evidence.

## Results

| Scenario | Risk/trade | Geom month | Best month | Worst month | Max DD | Trades | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `core3_0_25pct` | `0.25%` | `2.22%` | `7.33%` | `-1.90%` | `6.82%` | `916` | too small |
| `core3_1_00pct` | `1.00%` | `8.49%` | `30.24%` | `-7.96%` | `25.15%` | `916` | fails DD |
| `core3_2_00pct` | `2.00%` | `15.88%` | `62.07%` | `-16.62%` | `45.01%` | `916` | fails DD |
| `core3_4_00pct` | `4.00%` | `26.88%` | `126.50%` | `-34.59%` | `71.87%` | `916` | fails target/DD |
| `core3_5_00pct` | `5.00%` | `30.38%` | `168.35%` | `-43.30%` | `80.39%` | `916` | fails DD |
| `core4_5_00pct` | `5.00%` | `27.37%` | `197.53%` | `-64.94%` | `87.46%` | `1288` | fails target/DD |
| `core3_rank1_2_00pct` | `2.00%` | `8.69%` | `58.72%` | `-18.84%` | `55.23%` | `819` | fails target/DD |
| `core3_prob60_1_00pct` | `1.00%` | `1.18%` | `18.11%` | `-6.68%` | `8.81%` | `102` | fails target/window |
| `core3_expected0_1_00pct` | `1.00%` | `0.85%` | `17.89%` | `-6.23%` | `13.13%` | `157` | fails target/window |

## Interpretation

The current positive edge is real but not large enough for `30%` monthly returns at a sane account
risk. The core-3 candidate reaches the monthly target only at `5%` account risk per accepted trade,
and that produces `80.39%` historical max drawdown plus a `-43.30%` worst month. That is not a
paper-trading candidate.

The high-conviction subsets did not rescue the objective:

- rank-1 only reduced growth and still had very high drawdown at aggressive risk;
- probability `>= 0.60` and expected-R `>= 0` produced sparse samples and worse monthly growth;
- the selected model's probability/expected-R ordering is not strong enough to isolate a
  high-return, low-drawdown subset.

This means the next step should not be higher leverage or a nearby threshold sweep. The system needs
a different source of edge or a materially better exit model before a `30%` monthly objective is
credible.

## Decision

Reject CT-186 as a working or paper candidate.

Do not change the CT-184 paper timer from this evidence.

Keep CT-113 open and move to a new hypothesis focused on better edge quality, not risk
amplification.
