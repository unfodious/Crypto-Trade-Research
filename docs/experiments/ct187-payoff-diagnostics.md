# CT-187 Payoff Diagnostics

Status: rejected as a higher-payoff exit path; research-only evidence.

CT-186 showed that the current CT-180/CT-184 signal stream reaches `30%` geometric monthly return
only by using extreme risk with unacceptable drawdown. CT-187 checks whether the same entries contain
enough larger favorable moves to justify a higher-payoff exit path instead of higher sizing.

## Method

Input replay reports:

- `data/generated/ct180_2024h2_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025h1_oi_high_or_europe_replay/replay_report.json`
- `data/generated/ct180_2025julnov_oi_high_or_europe_replay/replay_report.json`

Config and generated report:

- `configs/ct187-payoff-diagnostics.json`
- `data/generated/ct187_payoff_diagnostics/report.json`
- `data/generated/ct187_payoff_diagnostics/report.md`

The diagnostic rebuilds accepted rows from replay `selected_trades.parquet`, applies the frozen pack
risk controls, applies the daily cap, then reads each accepted trade's path telemetry:

- `max_favorable_excursion_r`
- `max_adverse_excursion_r`
- `realized_r_after_costs`

The key runner test is `>= 3R` maximum favorable excursion without touching `-1R`. This is only a
path-potential diagnostic, not proof that a 3R target would have filled first on every row.

## Results

| Scenario | Trades | Avg R | Win rate | Stop touch | Clean `>=3R` runners | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `core3_daily_cap_10` | `916` | `0.1573` | `50.76%` | `29.69%` | `10.37%` | reject |
| `core4_daily_cap_10` | `1288` | `0.1181` | `49.22%` | `25.78%` | `8.23%` | reject |
| `core3_rank1_daily_cap_10` | `819` | `0.1035` | `49.08%` | `30.65%` | `10.62%` | reject |
| `core3_prob60_daily_cap_10` | `102` | `0.1630` | `46.08%` | `49.02%` | `19.61%` | reject/sparse |
| `core3_expected0_daily_cap_10` | `157` | `0.0919` | `47.13%` | `43.95%` | `18.47%` | reject/sparse |

Runner threshold detail:

| Scenario | Clean `>=2R` | Clean `>=3R` | Clean `>=4R` | Clean `>=5R` |
| --- | ---: | ---: | ---: | ---: |
| `core3_daily_cap_10` | `20.85%` | `10.37%` | `4.69%` | `2.51%` |
| `core4_daily_cap_10` | `17.00%` | `8.23%` | `3.57%` | `1.63%` |
| `core3_rank1_daily_cap_10` | `19.29%` | `10.62%` | `5.25%` | `2.69%` |
| `core3_prob60_daily_cap_10` | `25.49%` | `19.61%` | `14.71%` | `9.80%` |
| `core3_expected0_daily_cap_10` | `21.02%` | `18.47%` | `13.38%` | `7.01%` |

## Interpretation

The current entries do not have enough broad-sample runner potential to rescue the monthly target by
changing only the fixed exit to a larger payoff. The broad core-3/core-4 rows have only about
`8-10%` clean `>=3R` runners. The probability and positive expected-R subsets look more runner-rich,
but they are sparse and have much worse stop-touch rates.

This explains why simply trying to convert the existing 2R setup into 3R/4R targets is unlikely to
produce the desired monthly return with sane drawdown. The system needs different entries or
different market regimes that naturally create larger continuation moves.

## Decision

Reject CT-187 as a direct higher-payoff exit path for the current CT-180/CT-184 entry stream.

Do not change CT-184 paper exits or sizing from this evidence.

The next useful hypothesis should change the entry/timeframe family, for example a higher-timeframe
continuation setup where `>=3R` favorable moves are structurally more common.
