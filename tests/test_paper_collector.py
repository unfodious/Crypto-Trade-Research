import json
from pathlib import Path

from crypto_trade_research.models.artifacts import (
    ExpectedRidgeArtifact,
    FeatureSchema,
    ModelArtifact,
    MultifeatureRidgeArtifact,
    write_model_artifact,
)
from crypto_trade_research.paper_collector import (
    PaperCollectorConfig,
    run_paper_collector,
    write_rows_parquet,
)


def test_run_paper_collector_generates_ranked_signals_and_paper_ledger(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    payload = run_paper_collector(config)

    assert payload["schema_version"] == "research.paper-signal-ledger.v1"
    assert payload["summary"]["decision_time"] == "2026-05-27T00:02:00Z"
    assert payload["summary"]["take_count"] == 1
    assert payload["safety"]["live_order_authority"] is False
    assert payload["signals"][0]["contract_version"] == "ml-inference.v1"
    assert payload["signals"][0]["recommended_action"] == "take"
    assert payload["signals"][0]["reason_codes"] == [
        "expected_r_above_threshold",
        "rank_within_top_n",
    ]
    assert payload["trades"][0]["paper_status"] == "closed"
    assert payload["trades"][0]["net_r"] == 1.25
    assert (config.output_dir / "signals.json").exists()
    assert (config.output_dir / "ledger.json").exists()


def test_run_paper_collector_blocks_abstention_filtered_take(tmp_path: Path) -> None:
    config = _config(tmp_path, abstention_block=True)

    payload = run_paper_collector(config)

    assert payload["summary"]["take_count"] == 0
    assert payload["signals"][0]["recommended_action"] == "skip"
    assert payload["signals"][0]["reason_codes"] == ["abstention_filter_block"]
    assert payload["signals"][0]["hard_risk_blocks"] == ["abstention_filter_block"]
    assert payload["signals"][0]["abstention"]["blocked"] is True
    assert payload["trades"] == []


def test_run_paper_collector_fails_closed_when_abstention_feature_missing(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, abstention_block=True, include_abstention_features=False)

    payload = run_paper_collector(config)

    assert payload["summary"]["take_count"] == 0
    assert payload["signals"][0]["recommended_action"] == "skip"
    assert payload["signals"][0]["reason_codes"] == ["missing_abstention_feature"]
    assert payload["signals"][0]["hard_risk_blocks"] == ["missing_abstention_feature"]
    assert payload["signals"][0]["abstention"]["missing_features"] == ["fm_oi_value_change_1h"]


def _config(
    tmp_path: Path,
    *,
    abstention_block: bool = False,
    include_abstention_features: bool = True,
) -> PaperCollectorConfig:
    model_path = _write_model_artifact(tmp_path)
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "candidate_name": "unit_candidate",
                "source_artifacts": {"model_artifact": {"path": str(model_path)}},
                "strategy": {
                    "side": "long",
                    "symbols": ["TONUSDT", "ICPUSDT"],
                    "filters": [
                        {"feature": "funding_rate", "operator": "<=", "value": -0.00002},
                        {
                            "feature": "funding_rate_zscore_20",
                            "operator": "<=",
                            "value": -0.25,
                        },
                        {"feature": "close_location", "operator": ">=", "value": 0.45},
                    ],
                    "ranking": {
                        "top_n_per_decision_time": 1,
                        "selected_expected_r_threshold": -0.2,
                    },
                    **(
                        {
                            "abstention_filter_groups": [
                                [
                                    {
                                        "feature": "fm_oi_value_change_1h",
                                        "operator": ">",
                                        "value": 0.015,
                                    }
                                ]
                            ]
                        }
                        if abstention_block
                        else {}
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    feature_path = tmp_path / "features.parquet"
    write_rows_parquet(
        feature_path,
        [
            _feature(
                "2026-05-27T00:01:00Z",
                "TONUSDT",
                -0.00003,
                -0.5,
                0.5,
                include_abstention_features=include_abstention_features,
            ),
            _feature(
                "2026-05-27T00:02:00Z",
                "TONUSDT",
                -0.00004,
                -0.6,
                0.6,
                include_abstention_features=include_abstention_features,
            ),
            _feature(
                "2026-05-27T00:02:00Z",
                "ICPUSDT",
                -0.00003,
                -0.4,
                0.5,
                include_abstention_features=include_abstention_features,
            ),
        ],
    )
    label_path = tmp_path / "labels.parquet"
    write_rows_parquet(
        label_path,
        [
            {
                "symbol": "TONUSDT",
                "decision_time": "2026-05-27T00:02:00Z",
                "realized_r_after_costs": 1.25,
                "target_before_stop": True,
                "entry_price": 1.0,
                "stop_price": 0.996,
                "target_price": 1.008,
            }
        ],
    )
    return PaperCollectorConfig.from_dict(
        {
            "run_name": "unit_paper_collector",
            "output_dir": str(tmp_path / "out"),
            "issue_id": "CT-136",
            "epic_id": "CT-113",
            "pack_manifest_path": str(pack_path),
            "feature_source_path": str(feature_path),
            "label_source_path": str(label_path),
            "decision_time": "2026-05-27T00:02:00Z" if abstention_block else None,
            "mode": "historical_dry_run",
        }
    )


def _feature(
    decision_time: str,
    symbol: str,
    funding_rate: float,
    funding_z: float,
    close_location: float,
    *,
    include_abstention_features: bool,
) -> dict[str, object]:
    row = {
        "symbol": symbol,
        "timeframe": "1m",
        "decision_time": decision_time,
        "source_available_at": decision_time,
        "funding_rate": funding_rate,
        "funding_rate_zscore_20": funding_z,
        "close_location": close_location,
        "hours_since_funding": 2.0,
        "risk_on_score_20": 0.6,
    }
    if include_abstention_features:
        row["fm_oi_value_change_1h"] = 0.02 if symbol == "TONUSDT" else 0.0
    return row


def _write_model_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "model_artifact.json"
    write_model_artifact(
        path,
        ModelArtifact(
            model_id="unit_candidate",
            model_version="20260527T000000Z",
            model=MultifeatureRidgeArtifact(
                feature_names=("funding_rate", "funding_rate_zscore_20", "close_location"),
                means={
                    "funding_rate": 0.0,
                    "funding_rate_zscore_20": 0.0,
                    "close_location": 0.5,
                },
                standard_deviations={
                    "funding_rate": 0.0001,
                    "funding_rate_zscore_20": 1.0,
                    "close_location": 0.1,
                },
                intercept=0.0,
                weights={
                    "funding_rate": -1.0,
                    "funding_rate_zscore_20": -0.2,
                    "close_location": 0.1,
                },
                probability_threshold=0.55,
            ),
            expected_r_model=ExpectedRidgeArtifact(
                feature_names=("funding_rate", "funding_rate_zscore_20", "close_location"),
                means={
                    "funding_rate": 0.0,
                    "funding_rate_zscore_20": 0.0,
                    "close_location": 0.5,
                },
                standard_deviations={
                    "funding_rate": 0.0001,
                    "funding_rate_zscore_20": 1.0,
                    "close_location": 0.1,
                },
                intercept=-0.4,
                weights={
                    "funding_rate": -1.0,
                    "funding_rate_zscore_20": -0.2,
                    "close_location": 0.1,
                },
                expected_r_threshold=-0.2,
            ),
            feature_schema=FeatureSchema(
                feature_set_version="features.unit.v1",
                feature_names=("funding_rate", "funding_rate_zscore_20", "close_location"),
            ),
            preprocessing={"missing_value_policy": "fail_closed"},
            calibration={"method": "unit"},
            dataset_manifest_path="data/generated/unit/manifest.json",
            training_data_hash="abc123",
            research_git_commit="abc123",
            dependency_versions={"python": "3.12"},
            created_at="2026-05-27T00:00:00Z",
        ),
    )
    return path
