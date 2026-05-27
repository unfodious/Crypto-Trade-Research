# CT-167 Forward Filter Diagnostics

Date: 2026-05-27

Issue: CT-167

Epic: CT-113

## Goal

CT-145 and CT-156 forward-paper streams were still producing zero candidates after CT-166 fixed
Decimal funding feature generation. CT-167 adds diagnostics that explain where candidates are
filtered out instead of treating `candidate_count=0` as an opaque result.

## Implementation

Added `crypto-trade-build-forward-filter-diagnostics`, configured by
`configs/ct167-forward-filter-diagnostics.json`.

For each forward-paper stream the report records:

- configured strategy row count;
- final candidate count;
- independent pass count per pack filter;
- sequential before/after counts per pack filter;
- missing feature count per filter;
- observed min/max feature values.

The tool is read-only. It does not change pack filters, write paper trades, alter runtime order
placement, or approve live trading.

## Local Smoke

Command:

```sh
scripts/run_ct167_forward_filter_diagnostics_once.sh
```

Result:

- total strategy rows: 11
- total final candidates: 0
- CT-145 decision time: `2026-05-27T14:45:00Z`
- CT-156 decision time: `2026-05-27T14:45:00Z`

CT-145:

- `funding_rate <= -2e-05`: independent 2, sequential 5 -> 2, missing 0
- `funding_rate_zscore_20 <= -0.25`: independent 4, sequential 2 -> 2, missing 0
- `close_location >= 0.45`: independent 5, sequential 2 -> 2, missing 0
- `risk_on_score_20 >= 0.35`: independent 5, sequential 2 -> 2, missing 0
- `mtf_5m_risk_on_score_20 >= 0.35`: independent 0, sequential 2 -> 0, missing 0

CT-156:

- `funding_rate <= -2e-05`: independent 3, sequential 6 -> 3, missing 0
- `funding_rate_zscore_20 <= -0.25`: independent 5, sequential 3 -> 3, missing 0
- `close_location >= 0.45`: independent 5, sequential 3 -> 2, missing 0
- `risk_on_score_20 >= 0.35`: independent 6, sequential 2 -> 2, missing 0
- `mtf_5m_risk_on_score_20 >= 0.35`: independent 0, sequential 2 -> 0, missing 0

## Droplet Smoke

Command:

```sh
scripts/run_ct167_forward_filter_diagnostics_once.sh
```

Result:

- total strategy rows: 11
- total final candidates: 0
- CT-145 decision time: `2026-05-27T14:46:00Z`
- CT-156 decision time: `2026-05-27T14:46:00Z`

Droplet diagnostics match local evidence: funding and local risk-on fields are populated, while
the 5m MTF risk-on filter rejects every remaining row.

## Interpretation

The current zero-signal state is no longer explained by missing funding data. The active blocker is
the `mtf_5m_risk_on_score_20 >= 0.35` gate: in the latest forward rows its observed value is below
the configured threshold, so all otherwise eligible rows are rejected.

This does not justify simply loosening the filter in the live paper pack. The safer next step is a
separate historical validation issue that tests whether the MTF risk-on gate should be retuned,
removed, or replaced with a ranking/abstention rule while preserving the CT-113 gates.

## Safety

CT-167 is research-only diagnostics. It does not place, cancel, resize, or close orders; it does not
change leverage, stops, take-profit handling, or Binance runtime behavior. No working model or live
trading approval is claimed.
