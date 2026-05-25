from datetime import UTC, datetime

from crypto_trade_research.tracking.registry import (
    CostAssumptions,
    ExperimentRecord,
    ModelVersion,
    PromotionGateInputs,
    TimeWindow,
    evaluate_promotion_gates,
    format_experiment_list,
    list_experiments,
    write_experiment_record,
)


def _record(decision: str = "promote_to_paper_trading") -> ExperimentRecord:
    gate_inputs = PromotionGateInputs(
        model_average_r=0.42,
        rule_only_average_r=0.18,
        naive_average_r=0.0,
        walk_forward_average_r=0.31,
        max_drawdown_pct=0.04,
        max_drawdown_duration_bars=3,
        max_allowed_drawdown_pct=0.08,
        max_allowed_drawdown_duration_bars=10,
        leakage_checks_passed=True,
        stability_checks_passed=True,
        paper_trading_plan_path="docs/paper-trading-plan.md",
    )
    decision_result = evaluate_promotion_gates(gate_inputs)
    if decision == "reject":
        decision_result = evaluate_promotion_gates(
            PromotionGateInputs(
                model_average_r=0.05,
                rule_only_average_r=0.18,
                naive_average_r=0.0,
                walk_forward_average_r=-0.01,
                max_drawdown_pct=0.12,
                max_drawdown_duration_bars=15,
                max_allowed_drawdown_pct=0.08,
                max_allowed_drawdown_duration_bars=10,
                leakage_checks_passed=True,
                stability_checks_passed=False,
                paper_trading_plan_path="",
            )
        )

    version = "2026-01-08T000000Z" if decision == "reject" else "2026-01-07T000000Z"
    created_at = (
        datetime(2026, 1, 8, tzinfo=UTC)
        if decision == "reject"
        else datetime(2026, 1, 7, tzinfo=UTC)
    )
    return ExperimentRecord(
        model=ModelVersion(
            model_id="linear_probability_threshold",
            version=version,
            model_type="linear_probability_threshold",
        ),
        research_git_commit="abc1234",
        dataset_manifest_path="data/generated/sample_market_dataset/manifest.json",
        dataset_manifest_version="sample_market_dataset@2026-01-01",
        feature_names=("setup_score", "noise"),
        feature_code_version="features.core.v1",
        label_config={
            "kind": "target_before_stop",
            "target_r": 1.5,
            "stop_r": 1.0,
            "horizon_bars": 12,
        },
        train_window=TimeWindow("2026-01-01T00:00:00Z", "2026-01-04T00:00:00Z"),
        validation_window=TimeWindow("2026-01-05T00:00:00Z", "2026-01-05T00:00:00Z"),
        test_window=TimeWindow("2026-01-06T00:00:00Z", "2026-01-06T00:00:00Z"),
        cost_assumptions=CostAssumptions(
            fee_bps=4.0,
            slippage_bps=3.0,
            funding_bps=0.0,
            notes="fake sample assumptions only",
        ),
        metrics={
            "average_r": gate_inputs.model_average_r,
            "max_drawdown_pct": gate_inputs.max_drawdown_pct,
            "walk_forward_average_r": gate_inputs.walk_forward_average_r,
        },
        walk_forward_report_path="data/generated/sample_backtest/report.json",
        decision=decision_result,
        created_at=created_at,
    )


def test_write_experiment_record_requires_complete_metadata(tmp_path) -> None:
    path = write_experiment_record(tmp_path, _record())

    assert path == tmp_path / "linear_probability_threshold" / "2026-01-07T000000Z" / "record.json"
    payload = path.read_text(encoding="utf-8")
    assert '"research_git_commit": "abc1234"' in payload
    assert '"dataset_manifest_version": "sample_market_dataset@2026-01-01"' in payload
    assert '"feature_code_version": "features.core.v1"' in payload
    assert '"decision": {' in payload


def test_promotion_gates_reject_fragile_or_underperforming_model() -> None:
    decision = evaluate_promotion_gates(
        PromotionGateInputs(
            model_average_r=0.05,
            rule_only_average_r=0.18,
            naive_average_r=0.0,
            walk_forward_average_r=-0.01,
            max_drawdown_pct=0.12,
            max_drawdown_duration_bars=15,
            max_allowed_drawdown_pct=0.08,
            max_allowed_drawdown_duration_bars=10,
            leakage_checks_passed=True,
            stability_checks_passed=False,
            paper_trading_plan_path="",
        )
    )

    assert decision.status == "reject"
    assert [gate.name for gate in decision.gates if not gate.passed] == [
        "beats_rule_only_and_naive_oos",
        "walk_forward_metrics_acceptable",
        "drawdown_within_limits",
        "stability_checks_pass",
        "paper_trading_plan_exists",
    ]


def test_list_command_highlights_promoted_and_rejected_statuses(tmp_path) -> None:
    write_experiment_record(tmp_path, _record())
    write_experiment_record(tmp_path, _record("reject"))

    records = list_experiments(tmp_path)
    table = format_experiment_list(records)

    assert [record.decision.status for record in records] == [
        "promote_to_paper_trading",
        "reject",
    ]
    assert "linear_probability_threshold" in table
    assert "PROMOTE_TO_PAPER_TRADING" in table
    assert "REJECT" in table
