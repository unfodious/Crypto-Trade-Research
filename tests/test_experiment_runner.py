import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from crypto_trade_research.experiments.runner import (
    BaselineExperimentConfig,
    run_baseline_experiment,
)
from crypto_trade_research.models import load_model_artifact


def test_runner_executes_dataset_to_registry_baseline_pipeline(tmp_path: Path) -> None:
    source_csv = tmp_path / "market_candles.csv"
    _write_market_csv(source_csv)
    output_dir = tmp_path / "experiment"
    registry_dir = tmp_path / "registry"

    result = run_baseline_experiment(
        BaselineExperimentConfig.from_dict(
            {
                "experiment_name": "unit_real_baseline",
                "source_csv": str(source_csv),
                "dataset_name": "unit_real_dataset",
                "generator_version": "unit.runner.v1",
                "generated_at": "2026-05-26T06:00:00Z",
                "symbols": ["BTCUSDT"],
                "timeframes": ["1m"],
                "feature": {
                    "feature_set_version": "features.unit.v1",
                    "rolling_window": 2,
                    "decision_feature": "return_1",
                },
                "label": {
                    "label_set_version": "labels.unit.v1",
                    "horizon_bars": 1,
                    "side": "long",
                    "stop_loss_pct": 0.01,
                    "target_pct": 0.02,
                    "cost_pct": 0.001,
                    "flat_threshold_pct": 0.0,
                },
                "splits": {
                    "strategy": "chronological",
                    "train_end": "2026-01-01T00:04:00Z",
                    "validation_end": "2026-01-01T00:06:00Z",
                    "test_end": "2026-01-01T00:07:00Z",
                },
                "baseline": {
                    "probability_threshold": 0.5,
                    "initial_equity": 10000,
                    "risk_per_trade_pct": 0.01,
                },
                "cost_assumptions": {
                    "fee_bps": 4.0,
                    "slippage_bps": 3.0,
                    "funding_bps": 0.0,
                    "notes": "unit test assumptions",
                },
                "output_dir": str(output_dir),
                "registry_dir": str(registry_dir),
                "research_git_commit": "unitcommit",
            }
        )
    )

    assert result.dataset_manifest_path.exists()
    assert result.features_path.exists()
    assert result.labels_path.exists()
    assert result.baseline_report_path.exists()
    assert result.model_artifact_path.exists()
    assert result.promotion_checklist_path.exists()
    assert result.registry_record_path.exists()

    features = pq.read_table(result.features_path).to_pylist()
    labels = pq.read_table(result.labels_path).to_pylist()
    assert len(features) == 8
    assert len(labels) == 8
    assert all(row["source_available_at"] <= row["decision_time"] for row in features)

    report = json.loads(result.baseline_report_path.read_text(encoding="utf-8"))
    assert report["metadata"]["experiment_name"] == "unit_real_baseline"
    assert report["metadata"]["dataset_manifest_path"] == str(result.dataset_manifest_path)
    assert report["metadata"]["model_artifact_path"] == str(result.model_artifact_path)
    assert len(report["metadata"]["model_artifact_hash"]) == 64
    assert report["metadata"]["promotion_checklist_path"] == str(result.promotion_checklist_path)
    assert report["metadata"]["sample_count"] == 6
    assert report["splits"][0]["name"] == "train"
    assert report["strategies"]["rule_only_oos"]["sample_scope"] == "validation_test"
    assert report["strategies"]["linear_probability_oos"]["sample_scope"] == "validation_test"

    record = json.loads(result.registry_record_path.read_text(encoding="utf-8"))
    assert record["model"]["model_id"] == "unit_real_baseline"
    assert record["research_git_commit"] == "unitcommit"
    assert record["dataset_manifest_path"] == str(result.dataset_manifest_path)
    assert record["metrics"]["artifact_hash"] == report["metadata"]["model_artifact_hash"]
    assert record["metrics"]["promotion_checklist_path"] == str(result.promotion_checklist_path)
    assert record["decision"]["thresholds"]["min_oos_trade_count"] == 10
    assert record["feature_names"]
    assert record["decision"]["status"] == "reject"

    checklist = json.loads(result.promotion_checklist_path.read_text(encoding="utf-8"))
    assert checklist["status"] == "reject"
    assert checklist["thresholds"]["max_drawdown_pct"] == 0.0
    assert [gate["name"] for gate in checklist["gates"]] == [
        "beats_rule_only_and_naive_oos",
        "walk_forward_metrics_acceptable",
        "minimum_oos_trade_count",
        "drawdown_within_limits",
        "feature_leakage_checks_pass",
        "stability_checks_pass",
        "paper_trading_plan_exists",
    ]

    loaded_artifact = load_model_artifact(
        result.model_artifact_path,
        expected_feature_set_version="features.unit.v1",
        expected_feature_names=tuple(record["feature_names"]),
    )
    assert loaded_artifact.predict({"return_1": 0.05, "ma_2": 100.0}).recommended_action in {
        "take",
        "skip",
    }


def test_runner_refuses_shuffled_splits_for_performance_claims(tmp_path: Path) -> None:
    source_csv = tmp_path / "market_candles.csv"
    _write_market_csv(source_csv)
    config = BaselineExperimentConfig.from_dict(
        {
            "experiment_name": "bad_split",
            "source_csv": str(source_csv),
            "dataset_name": "bad_split_dataset",
            "generator_version": "unit.runner.v1",
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 2,
                "decision_feature": "return_1",
            },
            "label": {
                "label_set_version": "labels.unit.v1",
                "horizon_bars": 1,
                "side": "long",
                "stop_loss_pct": 0.01,
                "target_pct": 0.02,
                "cost_pct": 0.001,
                "flat_threshold_pct": 0.0,
            },
            "splits": {
                "strategy": "shuffle",
                "train_end": "2026-01-01T00:04:00Z",
                "validation_end": "2026-01-01T00:06:00Z",
                "test_end": "2026-01-01T00:07:00Z",
            },
            "output_dir": str(tmp_path / "experiment"),
            "registry_dir": str(tmp_path / "registry"),
        }
    )

    with pytest.raises(ValueError, match="shuffled splits are not allowed"):
        run_baseline_experiment(config)


def test_runner_applies_deterministic_candidate_setup_filters(tmp_path: Path) -> None:
    source_csv = tmp_path / "market_candles.csv"
    _write_market_csv(source_csv)
    output_dir = tmp_path / "experiment"

    result = run_baseline_experiment(
        BaselineExperimentConfig.from_dict(
            {
                "experiment_name": "unit_pullback_setup",
                "source_csv": str(source_csv),
                "dataset_name": "unit_real_dataset",
                "generator_version": "unit.runner.v1",
                "generated_at": "2026-05-26T06:00:00Z",
                "feature": {
                    "feature_set_version": "features.unit.v1",
                    "rolling_window": 2,
                    "decision_feature": "return_1",
                },
                "label": {
                    "label_set_version": "labels.unit.v1",
                    "horizon_bars": 1,
                    "side": "long",
                    "stop_loss_pct": 0.01,
                    "target_pct": 0.02,
                    "cost_pct": 0.001,
                    "flat_threshold_pct": 0.0,
                },
                "candidate_setup": {
                    "name": "negative_one_bar_pullback",
                    "filters": [
                        {
                            "feature": "return_1",
                            "operator": "<=",
                            "value": 0.0,
                        }
                    ],
                },
                "splits": {
                    "strategy": "chronological",
                    "train_end": "2026-01-01T00:04:00Z",
                    "validation_end": "2026-01-01T00:06:00Z",
                    "test_end": "2026-01-01T00:07:00Z",
                },
                "output_dir": str(output_dir),
                "registry_dir": str(tmp_path / "registry"),
                "research_git_commit": "unitcommit",
            }
        )
    )

    report = json.loads(result.baseline_report_path.read_text(encoding="utf-8"))
    assert report["metadata"]["candidate_setup"]["name"] == "negative_one_bar_pullback"
    assert report["metadata"]["sample_count"] == 3
    assert report["splits"][0]["row_count"] == 1

    record = json.loads(result.registry_record_path.read_text(encoding="utf-8"))
    assert record["metrics"]["candidate_setup_name"] == "negative_one_bar_pullback"
    assert record["metrics"]["candidate_sample_count"] == 3


def _write_market_csv(path: Path) -> None:
    header = [
        "schema_version",
        "venue",
        "market_type",
        "symbol",
        "base_asset",
        "quote_asset",
        "timeframe",
        "open_time",
        "close_time",
        "source_available_at",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "data_source",
        "source_file",
        "checksum",
    ]
    closes = [100.0, 103.0, 101.0, 104.0, 102.0, 105.0, 103.0, 106.0]
    rows = []
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index, close in enumerate(closes):
        open_time = start + timedelta(minutes=index)
        close_time = open_time + timedelta(minutes=1)
        rows.append(
            [
                "research.dataset.v1",
                "binance",
                "um_futures",
                "BTCUSDT",
                "BTC",
                "USDT",
                "1m",
                _fmt(open_time),
                _fmt(close_time),
                _fmt(close_time),
                f"{close - 1:.8f}",
                f"{close + 3:.8f}",
                f"{close - 2:.8f}",
                f"{close:.8f}",
                "100.0",
                f"{close * 100:.8f}",
                "100",
                "50.0",
                f"{close * 50:.8f}",
                "fixture:runner",
                "unit.csv",
                "sha256:unit",
            ]
        )
    path.write_text(
        ",".join(header) + "\n" + "\n".join(",".join(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _fmt(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
