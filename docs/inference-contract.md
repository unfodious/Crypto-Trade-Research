# ML Inference Contract

Contract version: `ml-inference.v1`

This contract describes how a promoted research model may produce a runtime signal for a future
paper-trading or live-reviewed integration. It is not a live execution interface.

## Boundary

`crypto-trade-research` may emit model estimates and a `take` or `skip` recommendation.
`crypto-trade` remains the only owner of account state, leverage, margin, order sizing, order
submission, stop loss, take profit, liquidation handling, reconciliation, and kill switches.

ML responses must never include direct order authority fields such as `leverage`, `order_size`,
`position_size`, `quantity`, `order_quantity`, `notional`, or `order_notional`.

## Request

Required request fields:

- `contract_version`: `ml-inference.v1`
- `request_id`
- `model_id`
- `model_version`
- `symbol`
- `timeframe`
- `signal_timestamp`
- `features_timestamp`
- `features_fresh_until`
- `feature_set_version`
- `feature_values`

Example: `tests/fixtures/inference_contract/request.v1.json`

## Response

Required response fields:

- `contract_version`
- `request_id`
- `model_id`
- `model_version`
- `symbol`
- `timeframe`
- `signal_timestamp`
- `features_timestamp`
- `data_freshness_seconds`
- `regime.label`
- `regime.probabilities`
- `expected_r`
- `target_before_stop_probability`
- `confidence`
- `recommended_action`: `take` or `skip`
- `reason_codes`
- `hard_risk_blocks`
- `generated_at`

Examples:

- `tests/fixtures/inference_contract/response-take.v1.json`
- `tests/fixtures/inference_contract/response-risk-block.v1.json`

## Failure Modes

The runtime must treat these as `skip` or no-signal conditions:

- `stale_model`: model version is not the active promoted version.
- `stale_data`: feature freshness does not cover `signal_timestamp`.
- `missing_feature`: a required feature is absent or null.
- `low_confidence`: confidence or calibration score is below the configured threshold.
- `service_unavailable`: model service or file export cannot be read.
- `model_not_promoted`: registry status is not `promote_to_paper_trading`.
- `risk_blocked`: deterministic runtime risk gates blocked the signal.

If `hard_risk_blocks` is non-empty, `recommended_action` must be `skip`.

`data_freshness_seconds` must equal `signal_timestamp - features_timestamp`. If a runtime
freshness threshold is configured and the response is stale, the response must set
`recommended_action` to `skip` and include `stale_data` in both `reason_codes` and
`hard_risk_blocks`.

## CT-180 Shadow Abstention Context

The CT-180/CT-181 shadow paper pack extends the signal payload with an observation-only
`abstention` object:

- `blocked`
- `filter_matched`
- `missing_features`

Required point-in-time abstention features:

- `fm_oi_value_change_1h`
- `fm_session_asia`
- `fm_session_europe`
- `fm_session_us`

For CT-180, `recommended_action` must be `skip` when `fm_oi_value_change_1h > 0.015`, when
`fm_session_europe >= 1`, or when any required abstention feature is missing. Missing abstention
features must add `missing_abstention_feature` to `hard_risk_blocks`. A matched abstention filter
must add `abstention_filter_block` to `hard_risk_blocks`.

## Export Options

Supported future implementation paths:

- JSON export for simple deterministic models.
- ONNX export when the Go runtime has a reviewed inference path.
- Local HTTP/gRPC model service with a narrow request/response contract.
- Periodic signal files for fake or paper trading only.

Actual production inference, live orders, and order-size authority are out of scope for CT-44.
