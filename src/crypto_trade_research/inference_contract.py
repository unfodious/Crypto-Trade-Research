"""Research-to-runtime inference contract validation."""

from datetime import datetime
from typing import Any

CONTRACT_VERSION = "ml-inference.v1"

_REQUIRED_REQUEST_FIELDS = {
    "contract_version",
    "request_id",
    "model_id",
    "model_version",
    "symbol",
    "timeframe",
    "signal_timestamp",
    "features_timestamp",
    "features_fresh_until",
    "feature_set_version",
    "feature_values",
}

_REQUIRED_RESPONSE_FIELDS = {
    "contract_version",
    "request_id",
    "model_id",
    "model_version",
    "symbol",
    "timeframe",
    "signal_timestamp",
    "features_timestamp",
    "data_freshness_seconds",
    "regime",
    "expected_r",
    "target_before_stop_probability",
    "confidence",
    "recommended_action",
    "reason_codes",
    "hard_risk_blocks",
    "generated_at",
}

_FORBIDDEN_ML_AUTHORITY_FIELDS = {
    "leverage",
    "order_size",
    "position_size",
    "quantity",
    "order_quantity",
    "notional",
    "order_notional",
}


def validate_inference_request(payload: dict[str, Any]) -> None:
    _require_fields(payload, _REQUIRED_REQUEST_FIELDS)
    _require_contract_version(payload)
    _require_non_empty_strings(
        payload,
        (
            "request_id",
            "model_id",
            "model_version",
            "symbol",
            "timeframe",
            "feature_set_version",
        ),
    )
    signal_timestamp = _parse_timestamp(payload["signal_timestamp"], "signal_timestamp")
    features_timestamp = _parse_timestamp(payload["features_timestamp"], "features_timestamp")
    features_fresh_until = _parse_timestamp(payload["features_fresh_until"], "features_fresh_until")
    if features_timestamp > signal_timestamp:
        raise ValueError("features_timestamp must not be after signal_timestamp")
    if features_fresh_until < signal_timestamp:
        raise ValueError("features_fresh_until must cover signal_timestamp")
    if not isinstance(payload["feature_values"], dict) or not payload["feature_values"]:
        raise ValueError("feature_values must be a non-empty object")


def validate_inference_response(payload: dict[str, Any]) -> None:
    _reject_forbidden_authority_fields(payload)
    _require_fields(payload, _REQUIRED_RESPONSE_FIELDS)
    _require_contract_version(payload)
    _require_non_empty_strings(
        payload,
        (
            "request_id",
            "model_id",
            "model_version",
            "symbol",
            "timeframe",
        ),
    )
    _parse_timestamp(payload["signal_timestamp"], "signal_timestamp")
    _parse_timestamp(payload["features_timestamp"], "features_timestamp")
    _parse_timestamp(payload["generated_at"], "generated_at")
    _require_probability(
        payload["target_before_stop_probability"],
        "target_before_stop_probability",
    )
    _require_probability(payload["confidence"], "confidence")
    if float(payload["data_freshness_seconds"]) < 0:
        raise ValueError("data_freshness_seconds must be non-negative")
    if payload["recommended_action"] not in {"take", "skip"}:
        raise ValueError("recommended_action must be take or skip")
    if not isinstance(payload["reason_codes"], list) or not payload["reason_codes"]:
        raise ValueError("reason_codes must be a non-empty list")
    if not isinstance(payload["hard_risk_blocks"], list):
        raise ValueError("hard_risk_blocks must be a list")
    if payload["hard_risk_blocks"] and payload["recommended_action"] != "skip":
        raise ValueError("hard_risk_blocks require recommended_action=skip")
    _validate_regime(payload["regime"])


def _reject_forbidden_authority_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _FORBIDDEN_ML_AUTHORITY_FIELDS:
                raise ValueError(f"forbidden ML authority field at {path}.{key}")
            _reject_forbidden_authority_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_authority_fields(item, f"{path}[{index}]")


def _require_fields(payload: dict[str, Any], required_fields: set[str]) -> None:
    missing = sorted(required_fields - payload.keys())
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))


def _require_contract_version(payload: dict[str, Any]) -> None:
    if payload["contract_version"] != CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {CONTRACT_VERSION}")


def _require_non_empty_strings(payload: dict[str, Any], field_names: tuple[str, ...]) -> None:
    for field_name in field_names:
        value = payload[field_name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must be an RFC3339 UTC timestamp ending with Z")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_probability(value: Any, field_name: str) -> None:
    number = float(value)
    if not 0 <= number <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1")


def _validate_regime(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("regime must be an object")
    if not isinstance(value.get("label"), str) or not value["label"].strip():
        raise ValueError("regime.label must be a non-empty string")
    probabilities = value.get("probabilities")
    if not isinstance(probabilities, dict) or not probabilities:
        raise ValueError("regime.probabilities must be a non-empty object")
    for name, probability in probabilities.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("regime probability names must be non-empty strings")
        _require_probability(probability, f"regime.probabilities.{name}")
