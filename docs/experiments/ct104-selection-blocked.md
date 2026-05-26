# CT-104 Candidate Selection Blocked

Date: 2026-05-26

## Decision

No CT-96 candidate is selected for paper-trading promotion.

CT-104 is therefore closed as a selection block rather than a frozen promoted artifact. Freezing a
`promote_to_paper_trading` registry record would be misleading because all expanded candidates from
CT-101 and CT-102 were rejected, and CT-103 stability gates reject the least-bad CT-102 row.

## Evidence Chain

- Dataset quality: `docs/audit/2026-05-26-ct99-expanded-dataset-quality-audit.md`
- Batch runner and leaderboard support: CT-100
- High-range short-fade matrix: `docs/experiments/ct101-expanded-short-fade-matrix.md`
- Complementary setup matrix: `docs/experiments/ct102-complementary-expanded-matrix.md`
- Stability and drawdown gates: `docs/experiments/ct103-stability-drawdown-gates.md`

## Least-Bad Candidate

The least-bad candidate after CT-102 was `ct102_volume_long_continuation_h24`.

- Registry path:
  `data/generated/experiment_registry/ct102_volume_long_continuation_h24/20260526T112100Z/record.json`
- Artifact path: `data/generated/ct102_volume_long_continuation_h24/model_artifact.json`
- Artifact hash: `006aacf3f705b77c3fc4e9a98ae872231fc559ef251998056be5669938f63796`
- Dataset manifest: `data/generated/ct96_expanded_core_futures_dataset/manifest.json`
- Feature set: `features.ct102.complementary.v1`
- Registry status: `reject`
- Model OOS average R: `-0.4576`
- Rule-only OOS average R: `-0.5360`
- Max drawdown: `99.9999%`

It beat rule-only, but both model and rule-only were negative. It also failed CT-103 gates for
positive OOS expectancy, drawdown, symbol breadth, session breadth, lucky-day concentration, and
nearby sensitivity.

## Artifact Contract Check

The rejected artifact was loaded with `load_model_artifact` as a contract sanity check. The loader
accepted the artifact hash, the prediction API returned only `skip` for the zero-feature probe, and
the artifact payload did not contain forbidden live authority or secret fields such as leverage,
quantity, notional, API keys, tokens, or secrets.

Expected feature names:

- `candle_body_pct`
- `close_location`
- `distance_from_rolling_high`
- `distance_from_rolling_low`
- `lower_wick_ratio`
- `ma_20`
- `ma_slope_20`
- `range_position_20`
- `return_1`
- `roc_2`
- `upper_wick_ratio`
- `volatility_expansion_20`
- `volume_zscore_20`
- `warmup_missing_bars`

The generated artifact metadata contains `research_git_commit: unknown` because the CT-102 Docker
experiment run did not install `git` inside the container. This is acceptable for a rejected local
artifact, but it is a hard blocker for any future promoted artifact. Promotion evidence must be
regenerated in a container with `git` installed so artifact and registry records capture the exact
research commit.

## Selection Outcome

Do not prepare a paper-trading pack from CT-96 expanded evidence. CT-105 should document the
promotion block instead of fabricating a pack for a rejected candidate.
