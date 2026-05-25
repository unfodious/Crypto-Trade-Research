import json
from pathlib import Path

import pytest

from crypto_trade_research.inference_contract import (
    validate_inference_request,
    validate_inference_response,
)

FIXTURES = Path(__file__).parent / "fixtures" / "inference_contract"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_example_request_and_response_fixtures_validate() -> None:
    validate_inference_request(_fixture("request.v1.json"))
    validate_inference_response(_fixture("response-take.v1.json"))
    validate_inference_response(_fixture("response-risk-block.v1.json"))


def test_response_rejects_direct_order_authority_fields() -> None:
    payload = _fixture("response-take.v1.json")
    payload["leverage"] = 3

    with pytest.raises(ValueError, match="forbidden ML authority field"):
        validate_inference_response(payload)


def test_risk_block_response_must_skip_and_explain_failure_mode() -> None:
    payload = _fixture("response-risk-block.v1.json")

    assert payload["recommended_action"] == "skip"
    assert "stale_data" in payload["hard_risk_blocks"]
    assert "stale_data" in payload["reason_codes"]
    validate_inference_response(payload, max_freshness_seconds=60)


def test_response_rejects_inconsistent_freshness_seconds() -> None:
    payload = _fixture("response-take.v1.json")
    payload["data_freshness_seconds"] = 30

    with pytest.raises(ValueError, match="data_freshness_seconds must equal"):
        validate_inference_response(payload)


def test_stale_response_must_skip_with_stale_data_block_when_threshold_is_set() -> None:
    payload = _fixture("response-risk-block.v1.json")
    payload["recommended_action"] = "take"
    payload["hard_risk_blocks"] = []

    with pytest.raises(ValueError, match="stale responses must skip"):
        validate_inference_response(payload, max_freshness_seconds=60)
