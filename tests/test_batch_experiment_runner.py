import json
from pathlib import Path
from types import SimpleNamespace

from crypto_trade_research.experiments.batch import (
    BatchExperimentMatrix,
    leaderboard_row_from_record,
    run_experiment_batch,
)


def test_leaderboard_row_from_record_aggregates_failed_gates(tmp_path: Path) -> None:
    record_path = tmp_path / "registry" / "candidate_a" / "20260526T100000Z" / "record.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(
            {
                "model": {
                    "model_id": "candidate_a",
                    "version": "20260526T100000Z",
                    "model_type": "linear_probability_threshold",
                },
                "metrics": {
                    "average_r": 0.12,
                    "rule_only_average_r": 0.08,
                    "trade_count": 42,
                    "max_drawdown_pct": 0.031,
                    "artifact_hash": "a" * 64,
                },
                "decision": {
                    "status": "reject",
                    "gates": [
                        {"name": "beats_rule_only_and_naive_oos", "passed": True},
                        {"name": "stability_checks_pass", "passed": False},
                        {"name": "paper_trading_plan_exists", "passed": False},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    row = leaderboard_row_from_record(
        config={
            "experiment_name": "candidate_a",
            "symbols": ["SOLUSDT", "SUIUSDT"],
        },
        registry_record_path=record_path,
    )

    assert row["experiment_name"] == "candidate_a"
    assert row["run_status"] == "completed"
    assert row["decision"] == "reject"
    assert row["failed_gates"] == ["stability_checks_pass", "paper_trading_plan_exists"]
    assert row["oos_model_average_r"] == 0.12
    assert row["oos_rule_only_average_r"] == 0.08
    assert row["trade_count"] == 42
    assert row["max_drawdown_pct"] == 0.031
    assert row["symbol_coverage"] == "SOLUSDT,SUIUSDT"
    assert row["artifact_hash"] == "a" * 64
    assert row["registry_path"] == str(record_path)


def test_batch_runner_keeps_successful_rows_when_one_config_fails(tmp_path: Path) -> None:
    first_config = tmp_path / "first.json"
    second_config = tmp_path / "second.json"
    first_config.write_text(
        json.dumps(
            {
                "experiment_name": "candidate_a",
                "symbols": ["BTCUSDT"],
            }
        ),
        encoding="utf-8",
    )
    second_config.write_text(
        json.dumps(
            {
                "experiment_name": "candidate_b",
                "symbols": ["ETHUSDT"],
            }
        ),
        encoding="utf-8",
    )
    registry_record_path = tmp_path / "registry" / "candidate_a" / "v1" / "record.json"
    registry_record_path.parent.mkdir(parents=True)
    registry_record_path.write_text(
        json.dumps(
            {
                "model": {
                    "model_id": "candidate_a",
                    "version": "v1",
                    "model_type": "linear_probability_threshold",
                },
                "metrics": {
                    "average_r": 0.03,
                    "rule_only_average_r": -0.01,
                    "trade_count": 11,
                    "max_drawdown_pct": 0.02,
                    "artifact_hash": "b" * 64,
                },
                "decision": {
                    "status": "promote_to_paper_trading",
                    "gates": [
                        {"name": "beats_rule_only_and_naive_oos", "passed": True},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    leaderboard_path = tmp_path / "leaderboard.json"
    markdown_path = tmp_path / "leaderboard.md"

    def fake_runner(config: object) -> object:
        if config.experiment_name == "candidate_b":
            raise ValueError("dataset filters produced no market rows")
        return SimpleNamespace(registry_record_path=registry_record_path)

    result = run_experiment_batch(
        BatchExperimentMatrix.from_dict(
            {
                "experiments": [
                    {"config": str(first_config)},
                    {"config": str(second_config)},
                ],
                "leaderboard_path": str(leaderboard_path),
                "markdown_path": str(markdown_path),
            }
        ),
        runner=fake_runner,
    )

    payload = json.loads(leaderboard_path.read_text(encoding="utf-8"))
    assert result.completed_count == 1
    assert result.failed_count == 1
    assert payload["summary"] == {"completed": 1, "failed": 1, "total": 2}
    assert [row["experiment_name"] for row in payload["rows"]] == [
        "candidate_a",
        "candidate_b",
    ]
    assert payload["rows"][0]["decision"] == "promote_to_paper_trading"
    assert payload["rows"][1]["run_status"] == "failed"
    assert payload["rows"][1]["error"] == "dataset filters produced no market rows"
    assert "candidate_b" in markdown_path.read_text(encoding="utf-8")


def test_batch_runner_applies_matrix_overrides_before_running(tmp_path: Path) -> None:
    config_path = tmp_path / "base.json"
    config_path.write_text(
        json.dumps(
            {
                "experiment_name": "base_candidate",
                "symbols": ["BTCUSDT"],
                "baseline": {
                    "probability_threshold": 0.50,
                },
                "candidate_setup": {
                    "name": "base_setup",
                    "filters": [
                        {
                            "feature": "range_position_20",
                            "operator": ">=",
                            "value": 0.70,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    registry_record_path = tmp_path / "registry" / "candidate_override" / "v1" / "record.json"
    registry_record_path.parent.mkdir(parents=True)
    registry_record_path.write_text(
        json.dumps(
            {
                "model": {
                    "model_id": "candidate_override",
                    "version": "v1",
                    "model_type": "linear_probability_threshold",
                },
                "metrics": {
                    "average_r": 0.01,
                    "rule_only_average_r": 0.02,
                    "trade_count": 9,
                    "max_drawdown_pct": 0.04,
                    "artifact_hash": "c" * 64,
                },
                "decision": {
                    "status": "reject",
                    "gates": [
                        {"name": "beats_rule_only_and_naive_oos", "passed": False},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    seen_configs = []

    def fake_runner(config: object) -> object:
        seen_configs.append(config)
        return SimpleNamespace(registry_record_path=registry_record_path)

    run_experiment_batch(
        BatchExperimentMatrix.from_dict(
            {
                "experiments": [
                    {
                        "config": str(config_path),
                        "overrides": {
                            "experiment_name": "candidate_override",
                            "baseline": {
                                "probability_threshold": 0.60,
                            },
                            "candidate_setup": {
                                "name": "range_high_short_fade_ge_0_80",
                                "filters": [
                                    {
                                        "feature": "range_position_20",
                                        "operator": ">=",
                                        "value": 0.80,
                                    }
                                ],
                            },
                        },
                    }
                ],
                "leaderboard_path": str(tmp_path / "leaderboard.json"),
            }
        ),
        runner=fake_runner,
    )

    assert seen_configs[0].experiment_name == "candidate_override"
    assert seen_configs[0].baseline["probability_threshold"] == 0.60
    assert seen_configs[0].candidate_setup["name"] == "range_high_short_fade_ge_0_80"
    assert seen_configs[0].candidate_setup["filters"][0]["value"] == 0.80
