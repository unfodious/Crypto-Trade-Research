# CT-155 Crowding-Conditioned Negative-Funding Clusters

Date: 2026-05-27

Issue: CT-155

Epic: CT-113

## Decision

Validated the first three next research ideas as one controlled CT-113 branch:

1. crowded-short squeeze model;
2. crowding as abstention filter;
3. per-symbol / cluster models.

The immediate six-month historical validation supports the cluster thesis, especially high-beta
alts. It does not yet validate Binance crowding/top-trader fields, because those fields are being
collected forward and do not have enough point-in-time history for a non-leaky backtest.

CT-145 remains the primary active paper stream. CT-155 found a narrower alternative,
`ct155_high_beta_plus_dot`, that passed historical stability and should be prepared only as a
separate shadow paper stream in CT-156. Do not silently replace CT-145.

## Thesis

The negative-funding long edge behaves like a crowded-short / squeeze setup. It should work best
where short crowding meets enough beta and participation for forced covering. That suggests high-beta
L1/alt clusters should beat BTC/ETH majors and broad all-symbol averaging.

## Data And Constraints

Historical validation uses the same six-month point-in-time setup as CT-144:

- candle dataset: `ct121_six_month_core_futures_dataset`;
- funding dataset: `ct128_six_month_funding_rate_dataset`;
- train end: `2026-03-25T00:00:00Z`;
- validation end: `2026-04-25T00:00:00Z`;
- test end: `2026-05-25T00:00:00Z`.

Forward-only crowding inputs:

- CT-151/153 Binance crowding snapshots;
- current open interest, open-interest history, global long/short, top-trader position long/short,
  and top-trader account long/short;
- healthy snapshot count is `55` rows per run for the 11-symbol universe.

These crowding fields must not be backfilled into old CT-144 decisions. They can be used only after
enough forward snapshots exist.

## Implementation

Added configs:

- `configs/ct155-crowding-cluster-validation-matrix.json`;
- `configs/ct155-high-beta-plus-dot-detailed.json`.

Generated artifacts:

- `data/generated/ct155_crowding_cluster_validation/leaderboard.json`;
- `data/generated/ct155_high_beta_plus_dot_detailed/leaderboard.json`;
- `data/generated/ct155_high_beta_plus_dot_detailed/stability_report.json`.

Generated artifacts are not committed.

## Historical Cluster Matrix

All rows use the same negative-funding/risk-on rule family:

- `funding_rate <= -0.00002`;
- `funding_rate_zscore_20 <= -0.25`;
- `close_location >= 0.45`;
- `risk_on_score_20 >= 0.35`;
- `mtf_5m_risk_on_score_20 >= 0.35`;
- expected-R ridge ranking with validation-selected threshold and top-N controls.

| Experiment | Symbols | Avg R | Rule Avg R | Trades | Max DD | Selected E[R] | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| high-beta L1 no TON | SOL, SUI, AVAX, ADA, ICP | `0.3959` | `-0.4591` | `275` | `1.60%` | `-0.20` | keep CT-145 primary |
| clean momentum core | SOL, AVAX, ADA | `0.4355` | `-0.3557` | `190` | `1.58%` | `-0.20` | supports cluster thesis |
| high-beta plus DOT | SOL, SUI, AVAX, ADA, ICP, DOT | `0.4665` | `-0.4843` | `106` | `1.47%` | `-0.10` | shadow candidate |
| majors | BTC, ETH | `-0.1036` | `-0.5993` | `42` | `3.21%` | `-0.10` | reject |
| laggard/old alts | ATOM, XRP, TON, DOT | `0.2694` | `-0.5644` | `54` | `1.50%` | `-0.20` | sparse reject |
| all symbols | all 11 symbols | `0.2956` | `-0.5141` | `204` | `1.67%` | `-0.20` | diluted |

## Stability Check

`ct155_high_beta_plus_dot_detailed` passed explicit stability gates:

| Gate | Result |
| --- | --- |
| positive OOS expectancy | pass (`0.4665 > 0`) |
| beats rule-only OOS | pass (`0.4665 > -0.4843`) |
| minimum trade count | pass (`106 >= 100`) |
| drawdown within limit | pass (`1.47% <= 8.00%`) |
| symbol breadth | pass (`83.33% >= 50.00%`) |
| session breadth | pass (`66.67% >= 50.00%`) |
| lucky-day concentration | pass (`47.17% <= 75.00%`) |
| nearby sensitivity | pass (`100.00% >= 50.00%`) |

Symbol slices:

| Symbol | Trades | Avg R |
| --- | ---: | ---: |
| SOLUSDT | `14` | `1.1821` |
| ADAUSDT | `16` | `0.7000` |
| SUIUSDT | `13` | `0.6712` |
| ICPUSDT | `48` | `0.3875` |
| AVAXUSDT | `6` | `0.3250` |
| DOTUSDT | `9` | `-0.8417` |

The stability pass is real but narrow. DOT is negative as an individual slice; the row passes because
the broader high-beta basket offsets it and remains above the trade-count floor.

## Crowding Abstention Plan

Do not use CT-151/153 fields in historical CT-155 metrics yet. Use them forward only.

Once enough snapshots exist, test two pre-declared rules:

- squeeze confirmation: prefer negative-funding long signals when open interest rises and crowding
  shows shorts or reducing long dominance;
- abstention: skip otherwise valid CT-145/CT-155 signals when top-trader/global crowding is already
  aggressively long or OI/funding disagree with the squeeze thesis.

Minimum evidence before judging crowding:

- at least `14` calendar days of healthy `55`-row snapshots;
- no source gaps around candidate decision timestamps;
- compare CT-145/CT-155 signals with and without crowding filters;
- report skipped trade counterfactuals, avg R, drawdown, trade count, symbol/session breadth, and
  single-day concentration.

## Interpretation

The first three ideas are directionally useful:

- cluster selection clearly matters;
- BTC/ETH majors are not the right entry cluster for this setup;
- all-symbol averaging dilutes the edge;
- high-beta alt clusters are the right place to continue;
- crowding/top-trader should be treated as a future abstention/confirmation layer, not as a
  retroactive historical feature.

CT-155 does not approve live trading and does not mark CT-113 complete.

## Next Step

Created CT-156 to prepare a separate shadow paper pack for `ct155_high_beta_plus_dot`. CT-145 remains
the primary active paper stream until an explicit replacement decision is made.
