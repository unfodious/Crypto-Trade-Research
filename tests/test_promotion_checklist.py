import json
from pathlib import Path

CHECKLIST = Path(__file__).parents[1] / "templates" / "ml-promotion-checklist.v1.json"


def test_promotion_checklist_covers_required_rollout_stages_and_blocks() -> None:
    payload = json.loads(CHECKLIST.read_text(encoding="utf-8"))

    assert [stage["name"] for stage in payload["stages"]] == [
        "research_only",
        "fake_executor_replay",
        "paper_trading_dry_run",
        "shadow_mode",
        "tiny_size_pilot",
    ]
    assert all(stage["live_order_authority"] is False for stage in payload["stages"])
    assert set(payload["risk_controls"]["blocks"]) >= {
        "stale_data",
        "stale_model",
        "missing_feature",
        "exchange_api_error",
        "state_reconciliation_drift",
    }
    assert payload["risk_controls"]["kill_switch_required"] is True


def test_promotion_checklist_requires_secret_free_decision_logs_and_rollback() -> None:
    payload = json.loads(CHECKLIST.read_text(encoding="utf-8"))

    assert set(payload["log_fields"]) >= {
        "model_id",
        "model_version",
        "signal_timestamp",
        "features_timestamp",
        "recommended_action",
        "reason_codes",
        "hard_risk_blocks",
        "runtime_decision",
    }
    assert payload["secret_free_logging"] is True
    assert "disable_ml_influence" in payload["rollback"]["actions"]
    assert "require_operator_approval_before_resuming" in payload["rollback"]["actions"]
