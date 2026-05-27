import json
from pathlib import Path
from types import SimpleNamespace

import pyarrow.parquet as pq

import crypto_trade_research.experiments.batch as batch_module
from crypto_trade_research.experiments.batch import (
    BatchExperimentMatrix,
    _ExperimentInputCache,
    _write_parquet_atomic,
    leaderboard_row_from_record,
    run_experiment_batch,
)
from crypto_trade_research.features import FeatureFrame, FeatureManifest
from crypto_trade_research.labels import LabelFrame, LabelManifest


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


def test_experiment_input_cache_reuses_disk_artifacts_between_instances(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest_path = tmp_path / "dataset_manifest.json"
    funding_manifest_path = tmp_path / "funding_manifest.json"
    manifest_path.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest_path.write_text('{"funding": "unit"}', encoding="utf-8")
    source_rows = [{"symbol": "BTCUSDT", "timeframe": "1m"}]
    funding_rows = [{"symbol": "BTCUSDT"}]
    feature_frame = FeatureFrame(
        rows=[{"symbol": "BTCUSDT", "decision_time": "2026-01-01T00:01:00Z", "return_1": 0.1}],
        manifest=FeatureManifest(
            schema_version="research.dataset.v1",
            feature_set_version="features.unit.v1",
            generator_name="unit",
            row_count=1,
            features=(),
        ),
    )
    label_frame = LabelFrame(
        rows=[
            {
                "symbol": "BTCUSDT",
                "decision_time": "2026-01-01T00:01:00Z",
                "target_before_stop": True,
                "realized_r_after_costs": 1.0,
            }
        ],
        manifest=LabelManifest(
            schema_version="research.dataset.v1",
            label_set_version="labels.unit.v1",
            generator_name="unit",
            row_count=1,
            horizon_bars=1,
            side="long",
            labels=(),
        ),
    )
    config = _cache_unit_config(manifest_path, funding_manifest_path)

    monkeypatch.setattr(
        batch_module,
        "load_baseline_source_rows",
        lambda _: (manifest_path, source_rows),
    )
    monkeypatch.setattr(batch_module, "load_baseline_funding_rows", lambda _: funding_rows)
    monkeypatch.setattr(batch_module, "build_baseline_features", lambda *_: feature_frame)
    monkeypatch.setattr(batch_module, "build_baseline_candidate_labels", lambda *_: label_frame)

    first_inputs = _ExperimentInputCache(tmp_path / "cache").inputs_for(config)
    assert first_inputs.features.rows == feature_frame.rows
    assert first_inputs.labels.rows == label_frame.rows

    def fail_build(*_: object) -> object:
        raise AssertionError("cache miss")

    monkeypatch.setattr(batch_module, "build_baseline_features", fail_build)
    monkeypatch.setattr(batch_module, "build_baseline_candidate_labels", fail_build)

    second_inputs = _ExperimentInputCache(tmp_path / "cache").inputs_for(config)
    assert second_inputs.features.rows == feature_frame.rows
    assert second_inputs.labels.rows == label_frame.rows


def test_experiment_input_cache_key_changes_with_candidate_setup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest_path = tmp_path / "dataset_manifest.json"
    funding_manifest_path = tmp_path / "funding_manifest.json"
    manifest_path.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest_path.write_text('{"funding": "unit"}', encoding="utf-8")
    source_rows = [{"symbol": "BTCUSDT", "timeframe": "1m"}]
    feature_frame = FeatureFrame(
        rows=[{"symbol": "BTCUSDT", "decision_time": "2026-01-01T00:01:00Z", "return_1": 0.1}],
        manifest=FeatureManifest(
            schema_version="research.dataset.v1",
            feature_set_version="features.unit.v1",
            generator_name="unit",
            row_count=1,
            features=(),
        ),
    )
    first_label_frame = _label_frame("BTCUSDT")
    second_label_frame = _label_frame("ETHUSDT")
    label_calls = {"count": 0}

    def fake_labels(*_: object) -> LabelFrame:
        label_calls["count"] += 1
        return first_label_frame if label_calls["count"] == 1 else second_label_frame

    monkeypatch.setattr(
        batch_module,
        "load_baseline_source_rows",
        lambda _: (manifest_path, source_rows),
    )
    monkeypatch.setattr(batch_module, "load_baseline_funding_rows", lambda _: [])
    monkeypatch.setattr(batch_module, "build_baseline_features", lambda *_: feature_frame)
    monkeypatch.setattr(batch_module, "build_baseline_candidate_labels", fake_labels)

    cache = _ExperimentInputCache(tmp_path / "cache")
    first_inputs = cache.inputs_for(_cache_unit_config(manifest_path, funding_manifest_path))
    second_inputs = cache.inputs_for(
        _cache_unit_config(manifest_path, funding_manifest_path, candidate_symbols=("ETHUSDT",))
    )

    assert first_inputs.labels.rows[0]["symbol"] == "BTCUSDT"
    assert second_inputs.labels.rows[0]["symbol"] == "ETHUSDT"
    assert label_calls["count"] == 2


def test_write_parquet_atomic_streams_rows_across_chunks(tmp_path: Path) -> None:
    path = tmp_path / "rows.parquet"
    rows = [
        {
            "symbol": "BTCUSDT",
            "decision_time": f"2026-01-01T00:{index % 60:02d}:00Z",
            "return_1": index / 100_000,
        }
        for index in range(50_001)
    ]

    _write_parquet_atomic(path, rows)

    table = pq.read_table(path)
    assert table.num_rows == 50_001
    assert table.to_pylist()[0] == rows[0]
    assert table.to_pylist()[-1] == rows[-1]


def _cache_unit_config(
    manifest_path: Path,
    funding_manifest_path: Path,
    *,
    candidate_symbols: tuple[str, ...] = ("BTCUSDT",),
) -> SimpleNamespace:
    return SimpleNamespace(
        experiment_name="unit_cache",
        source_csv=None,
        dataset_manifest_path=manifest_path,
        funding_manifest_path=funding_manifest_path,
        dataset_name="unit_dataset",
        generator_version="unit.v1",
        symbols=("BTCUSDT", "ETHUSDT"),
        timeframes=("1m",),
        feature_set_version="features.unit.v1",
        rolling_window=2,
        higher_timeframes=(),
        label_generation_mode="candidate_only",
        label_config=SimpleNamespace(
            label_set_version="labels.unit.v1",
            horizon_bars=1,
            side="long",
            stop_loss_pct=0.01,
            target_pct=0.02,
            cost_pct=0.001,
            flat_threshold_pct=0.0,
            target_stop_tie_breaker="stop_first",
            exit_model="fixed_target_stop",
            breakeven_activation_r=None,
            breakeven_lock_r=0.0,
            trailing_stop_r=None,
        ),
        candidate_setup=SimpleNamespace(
            name="unit_setup",
            symbols=candidate_symbols,
            filters=(SimpleNamespace(feature="return_1", operator=">=", value=0.0),),
        ),
    )


def _label_frame(symbol: str) -> LabelFrame:
    return LabelFrame(
        rows=[
            {
                "symbol": symbol,
                "decision_time": "2026-01-01T00:01:00Z",
                "target_before_stop": True,
                "realized_r_after_costs": 1.0,
            }
        ],
        manifest=LabelManifest(
            schema_version="research.dataset.v1",
            label_set_version="labels.unit.v1",
            generator_name="unit",
            row_count=1,
            horizon_bars=1,
            side="long",
            labels=(),
        ),
    )
