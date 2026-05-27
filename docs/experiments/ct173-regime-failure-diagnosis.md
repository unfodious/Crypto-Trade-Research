# CT-173 Regime Failure Diagnosis

Status: diagnostic complete; no live approval.

CT-172 rejected the frozen CT-145 no-TON and CT-156 high-beta plus DOT paper candidates on the
pre-July 2025 holdout. CT-173 diagnoses why the same candidates looked strong in the original
selection slice and survived CT-169, but failed on January-June 2025.

This is a post-hoc diagnostic. It is not a new candidate, and it must not be used to approve live
trading.

## Evidence Windows

| Window | Evidence type | Date coverage | Candidate source |
| --- | --- | --- | --- |
| Jan-Jun 2025 | CT-172 untouched older holdout | `2025-01-08` to `2025-06-30` trade dates | frozen CT-145 / CT-156 packs |
| Jul-Nov 2025 | CT-169 older holdout | `2025-07-08` to `2025-11-24` trade dates | frozen CT-145 / CT-156 packs |
| Mar-May 2026 | original validation+test | `2026-03-25` to `2026-05-23` trade dates | CT-144 / CT-155 detailed runs |

## Headline Stability

| Candidate | Window | Trades | Avg R | Max DD | Profit factor |
| --- | --- | ---: | ---: | ---: | ---: |
| CT-145 no-TON | Jan-Jun 2025 | 2,242 | -0.0083 | 9.85% | 0.9849 |
| CT-145 no-TON | Jul-Nov 2025 | 1,255 | 0.0287 | 4.34% | 1.0558 |
| CT-145 no-TON | Mar-May 2026 | 275 | 0.3959 | 1.60% | 1.7073 |
| CT-156 high-beta+DOT | Jan-Jun 2025 | 1,096 | -0.0215 | 11.17% | 0.9654 |
| CT-156 high-beta+DOT | Jul-Nov 2025 | 672 | 0.0716 | 8.32% | 1.1248 |
| CT-156 high-beta+DOT | Mar-May 2026 | 106 | 0.4665 | 1.47% | 1.8768 |

The failure is not sparse. Jan-Jun 2025 has more than enough trades, so the rejection is about
stability and regime sensitivity, not lack of samples.

## Monthly Breakdown

CT-145 no-TON:

| Window | Month | Trades | Avg R | Profit factor |
| --- | --- | ---: | ---: | ---: |
| Jan-Jun 2025 | 2025-01 | 239 | 0.0851 | 1.147 |
| Jan-Jun 2025 | 2025-02 | 582 | -0.0312 | 0.949 |
| Jan-Jun 2025 | 2025-03 | 712 | -0.1477 | 0.756 |
| Jan-Jun 2025 | 2025-04 | 455 | 0.1653 | 1.361 |
| Jan-Jun 2025 | 2025-05 | 66 | -0.1794 | 0.619 |
| Jan-Jun 2025 | 2025-06 | 188 | 0.1119 | 1.329 |
| Jul-Nov 2025 | 2025-08 | 73 | 0.1039 | 1.296 |
| Jul-Nov 2025 | 2025-09 | 63 | -0.1818 | 0.601 |
| Jul-Nov 2025 | 2025-10 | 672 | 0.0454 | 1.093 |
| Jul-Nov 2025 | 2025-11 | 445 | 0.0218 | 1.037 |
| Mar-May 2026 | 2026-03 | 13 | -0.4827 | 0.466 |
| Mar-May 2026 | 2026-04 | 136 | 0.5015 | 1.967 |
| Mar-May 2026 | 2026-05 | 126 | 0.3726 | 1.655 |

CT-156 high-beta plus DOT:

| Window | Month | Trades | Avg R | Profit factor |
| --- | --- | ---: | ---: | ---: |
| Jan-Jun 2025 | 2025-01 | 148 | 0.2519 | 1.444 |
| Jan-Jun 2025 | 2025-02 | 316 | -0.1031 | 0.852 |
| Jan-Jun 2025 | 2025-03 | 336 | -0.1757 | 0.749 |
| Jan-Jun 2025 | 2025-04 | 198 | 0.1468 | 1.264 |
| Jan-Jun 2025 | 2025-05 | 37 | -0.0863 | 0.747 |
| Jan-Jun 2025 | 2025-06 | 61 | 0.0802 | 1.252 |
| Jul-Nov 2025 | 2025-08 | 10 | -0.1472 | 0.690 |
| Jul-Nov 2025 | 2025-09 | 8 | -0.7425 | 0.067 |
| Jul-Nov 2025 | 2025-10 | 358 | 0.2181 | 1.456 |
| Jul-Nov 2025 | 2025-11 | 296 | -0.0761 | 0.889 |
| Mar-May 2026 | 2026-03 | 6 | -0.6750 | 0.311 |
| Mar-May 2026 | 2026-04 | 43 | 0.5692 | 2.157 |
| Mar-May 2026 | 2026-05 | 57 | 0.5092 | 1.988 |

Diagnostic slices:

| Candidate | Slice | Trades | Avg R | Profit factor |
| --- | --- | ---: | ---: | ---: |
| CT-145 no-TON | Jan-Jun 2025, Feb-Mar only | 1,294 | -0.0953 | 0.843 |
| CT-145 no-TON | Jan-Jun 2025, excluding Feb-Mar | 948 | 0.1105 | 1.237 |
| CT-156 high-beta+DOT | Jan-Jun 2025, Feb-Mar only | 652 | -0.1405 | 0.799 |
| CT-156 high-beta+DOT | Jan-Jun 2025, excluding Feb-Mar | 444 | 0.1533 | 1.301 |
| CT-145 no-TON | Jul-Nov 2025, October only | 672 | 0.0454 | 1.093 |
| CT-145 no-TON | Jul-Nov 2025, excluding October | 583 | 0.0093 | 1.017 |
| CT-156 high-beta+DOT | Jul-Nov 2025, October only | 358 | 0.2181 | 1.456 |
| CT-156 high-beta+DOT | Jul-Nov 2025, excluding October | 314 | -0.0954 | 0.860 |
| CT-145 no-TON | Mar-May 2026, excluding March | 262 | 0.4395 | 1.810 |
| CT-156 high-beta+DOT | Mar-May 2026, excluding March | 100 | 0.5350 | 2.059 |

The candidates are damaged most by broad weak periods rather than by a single isolated outlier.
February-March 2025 explain the Jan-Jun rejection, and March 2026 was also negative before the
April-May positive cluster.

## Symbol Breakdown

| Candidate | Window | Positive symbols | Main drag |
| --- | --- | ---: | --- |
| CT-145 no-TON | Jan-Jun 2025 | 2 / 5 | `ADAUSDT` -0.1014R, `SUIUSDT` -0.0415R |
| CT-145 no-TON | Jul-Nov 2025 | 3 / 5 | `SOLUSDT` -0.0797R, `AVAXUSDT` -0.0299R |
| CT-145 no-TON | Mar-May 2026 | 5 / 5 | none |
| CT-156 high-beta+DOT | Jan-Jun 2025 | 2 / 6 | `ADAUSDT` -0.1603R, `SUIUSDT` -0.1526R |
| CT-156 high-beta+DOT | Jul-Nov 2025 | 3 / 6 | `DOTUSDT` -0.2664R, `SOLUSDT` -0.2101R |
| CT-156 high-beta+DOT | Mar-May 2026 | 5 / 6 | `DOTUSDT` -0.8417R |

There is no stable universal symbol fix. `AVAXUSDT` was strong in Jan-Jun 2025 and Mar-May 2026,
but was slightly negative in Jul-Nov 2025. `DOTUSDT` flipped from positive in Jan-Jun 2025 to deeply
negative in Jul-Nov 2025 and Mar-May 2026. Symbol re-selection alone is therefore likely another
overfit path unless it is validated on fresh data.

## Session Breakdown

| Candidate | Window | Asia Avg R | Europe Avg R | US Avg R |
| --- | --- | ---: | ---: | ---: |
| CT-145 no-TON | Jan-Jun 2025 | -0.0311 | 0.0268 | -0.0228 |
| CT-145 no-TON | Jul-Nov 2025 | 0.0127 | 0.0191 | 0.0581 |
| CT-145 no-TON | Mar-May 2026 | 0.4772 | 0.0250 | 0.5099 |
| CT-156 high-beta+DOT | Jan-Jun 2025 | 0.0102 | 0.0544 | -0.1210 |
| CT-156 high-beta+DOT | Jul-Nov 2025 | 0.1228 | 0.0552 | 0.0208 |
| CT-156 high-beta+DOT | Mar-May 2026 | -0.3568 | 0.2536 | 0.6493 |

The only slice that stayed positive in all three windows for both candidates was Europe session.
This is a useful diagnostic, but it is post-selection. It cannot be promoted without a new validation
layer.

## BTC / ETH Context

Monthly BTC/ETH context around the failure:

| Month | BTC return | ETH return | CT-145 Avg R | CT-156 Avg R |
| --- | ---: | ---: | ---: | ---: |
| 2025-02 | -17.6% | -32.2% | -0.0312 | -0.1031 |
| 2025-03 | -2.1% | -18.5% | -0.1477 | -0.1757 |
| 2025-04 | 14.1% | -1.6% | 0.1653 | 0.1468 |
| 2025-10 | -3.9% | -7.2% | 0.0454 | 0.2181 |
| 2026-03 | 2.0% | 7.3% | -0.4827 | -0.6750 |
| 2026-04 | 11.8% | 7.2% | 0.5015 | 0.5692 |
| 2026-05 | 0.9% | -7.0% | 0.3726 | 0.5092 |

The signal is not simply "longs work when BTC/ETH are up." October 2025 worked despite BTC/ETH
being down, likely because the negative-funding/risk-on setup was catching a specific rebound or
forced-positioning regime. However, sustained ETH-led weakness in February-March 2025 was clearly
toxic for the candidates.

## Interpretation

CT-172 is a real rejection of the current paper candidates:

- They fail on a high-trade-count older holdout, not on sparse evidence.
- They are strongly dependent on time regime.
- Symbol breadth is not stable enough to rescue them.
- The most stable post-hoc slice is Europe session, not an OHLCV indicator threshold.
- CT-156 is especially vulnerable to US-session Jan-Jun 2025 losses and DOT instability.

The most important lesson is not "loosen the filter" or "remove bad months." The lesson is that the
current CT-113 candidate family needs an explicit abstention or session/regime layer that is
validated outside the data used to discover it.

## Decision

No working model claim.

No paper-to-live promotion.

Keep CT-113 open.

Keep CT-145 and CT-156 forward-paper streams as observation-only, but downgrade confidence after the
CT-172 rejection.

## Next Step

Created CT-174 to test a predeclared Europe-session/regime-abstention hypothesis with a fresh
validation layer. The hypothesis must be treated as post-hoc until it survives either older untouched
history, forward evidence, or a stricter walk-forward design.
