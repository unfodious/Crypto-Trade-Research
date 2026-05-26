# CT-112 Regime-Aware Research Lessons

Date: 2026-05-26

## Final CT-107 Outcome

CT-107 did not produce a promoted paper-trading candidate.

The epic was still useful because it tested the next obvious idea after CT-96: adding explicit local
regime filters before taking long continuation or breakout trades.

Completed sequence:

- CT-108 defined the regime-aware hypothesis and blocked another blind CT-101/CT-102 threshold
  expansion.
- CT-109 added deterministic point-in-time regime features:
  `trend_above_ma_N`, `ma_slope_sign_N`, and `volatility_bucket_N`.
- CT-110 ran a controlled four-row matrix across trend-aligned continuation and trend-filtered
  volatility breakout at 12-bar and 24-bar horizons.
- CT-111 blocked selection because the least-bad row was still negative after costs and had
  near-total drawdown.

## Durable Lessons

- Local trend and volatility buckets are useful diagnostics, but they are not enough to turn the
  CT-96 long continuation/breakout families positive.
- A candidate can beat rule-only and still be rejected when both paths are negative after costs.
- The binding blocker remains drawdown, not trade count. CT-110 trade counts were meaningful, but
  max drawdown stayed around `98.68%` to `100.00%`.
- Nearby sensitivity failed: `0/4` CT-110 rows had positive model OOS average R.
- Do not repeat CT-110 H1/H2 with only minor thresholds around:
  - `volume_zscore_20 >= 1.0`,
  - `volatility_expansion_20 >= 1.3`,
  - `close_location >= 0.7`,
  - `trend_above_ma_20 == 1.0`,
  - `ma_slope_sign_20 >= 0.0` or `>= 1.0`,
  - `volatility_bucket_20 <= 2.0` or `== 2.0`.
- The next research iteration should change the risk model or information set, not only the local
  setup filters.

## Recommended Next Hypotheses

Prefer one of these before running another matrix:

- Market-reference regime: join BTC/ETH point-in-time reference state so alt trades can abstain
  during broad beta shocks.
- Cooldown or adaptive risk: stop taking repeated setup entries after recent realized drawdown,
  computed only from prior completed trades or strictly historical diagnostics.
- Directional expansion: test short-side or risk-off continuation separately instead of forcing
  every regime-aware setup into long-only continuation.
- Higher-timeframe context: add pre-declared 15m/1h context exported through the same dataset
  contract rather than deriving future-looking state from 1m labels.

## Reusable Commands

Run CT-110 matrix locally with exact git metadata in registry records:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'apt-get update >/tmp/apt.log && apt-get install -y git >/tmp/git.log && python -m pip install -e ".[dev]" >/tmp/pip.log && crypto-trade-run-batch-experiments --matrix configs/ct110-regime-aware-matrix.json'
```

Close-out verifier:

```sh
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -lc 'python -m pip install -e ".[dev]" >/tmp/pip.log && python -m pytest && ruff check . && ruff format --check .'
```

## Final Decision

CT-107 remains blocked from paper trading.

Do not prepare a paper-trading pack for CT-110/CT-111. Future work must define a new thesis that
changes the risk model, market-reference information, directionality, or timeframe context before
using the CT-96 expanded dataset again.
