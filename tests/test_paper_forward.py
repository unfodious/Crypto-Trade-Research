import json
from datetime import datetime, timedelta
from pathlib import Path

from crypto_trade_research.models.artifacts import (
    ExpectedRidgeArtifact,
    FeatureSchema,
    ModelArtifact,
    MultifeatureRidgeArtifact,
    write_model_artifact,
)
from crypto_trade_research.paper_forward import (
    ForwardPaperRunConfig,
    run_forward_paper_collection,
)
from crypto_trade_research.paper_trading import PaperTradingPackConfig, build_paper_trading_pack


def test_run_forward_paper_collection_uses_fresh_public_data_without_live_authority(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(tmp_path)
    config = ForwardPaperRunConfig.from_dict(
        {
            "run_name": "unit_forward",
            "output_dir": str(tmp_path / "forward"),
            "issue_id": "CT-137",
            "epic_id": "CT-113",
            "pack_manifest_path": str(pack_path),
            "symbols": ["TONUSDT", "BTCUSDT", "ETHUSDT"],
            "lookback_minutes": 30,
            "funding_lookback_hours": 200,
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "request_sleep_seconds": 0,
            "end_time": "2026-05-27T01:00:30Z",
        }
    )

    payload = run_forward_paper_collection(
        config,
        fetch_klines=_fake_klines,
        fetch_funding=_fake_funding,
    )

    assert payload["schema_version"] == "research.forward-paper-run.v1"
    assert payload["row_counts"]["latest_features"] == 3
    assert payload["collector_summary"]["mode"] == "forward_paper"
    assert payload["decision"]["live_trading_approved"] is False
    assert payload["decision"]["working_model"] is False
    assert payload["row_counts"]["open_trades"] == 1
    assert payload["row_counts"]["closed_trades"] == 0
    assert (config.output_dir / "signals.json").exists()
    assert (config.output_dir / "ledger.json").exists()
    assert (config.output_dir / "forward_signals.json").exists()
    assert (config.output_dir / "forward_ledger.json").exists()
    assert (config.output_dir / "monitoring_report.json").exists()

    follow_up_config = ForwardPaperRunConfig.from_dict(
        {
            "run_name": "unit_forward",
            "output_dir": str(tmp_path / "forward"),
            "issue_id": "CT-137",
            "epic_id": "CT-113",
            "pack_manifest_path": str(pack_path),
            "symbols": ["TONUSDT", "BTCUSDT", "ETHUSDT"],
            "lookback_minutes": 30,
            "funding_lookback_hours": 200,
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "request_sleep_seconds": 0,
            "end_time": "2026-05-27T01:20:30Z",
        }
    )

    follow_up = run_forward_paper_collection(
        follow_up_config,
        fetch_klines=_fake_klines,
        fetch_funding=_fake_funding,
    )

    assert follow_up["row_counts"]["closed_trades"] == 1
    assert follow_up["row_counts"]["open_trades"] == 1
    forward_ledger = json.loads((config.output_dir / "forward_ledger.json").read_text())
    closed = [trade for trade in forward_ledger["trades"] if trade["paper_status"] == "closed"]
    assert closed[0]["exit_reason"] in {"stop", "target", "horizon_exit"}
    assert closed[0]["live_order_authority"] is False


def _write_pack(tmp_path: Path) -> Path:
    model_path = tmp_path / "model_artifact.json"
    write_model_artifact(
        model_path,
        ModelArtifact(
            model_id="unit_candidate",
            model_version="20260527T000000Z",
            model=MultifeatureRidgeArtifact(
                feature_names=("close_location",),
                means={"close_location": 0.5},
                standard_deviations={"close_location": 0.1},
                intercept=0.0,
                weights={"close_location": 0.1},
                probability_threshold=0.49,
            ),
            expected_r_model=ExpectedRidgeArtifact(
                feature_names=("close_location",),
                means={"close_location": 0.5},
                standard_deviations={"close_location": 0.1},
                intercept=0.0,
                weights={"close_location": 0.1},
                expected_r_threshold=-1.0,
            ),
            feature_schema=FeatureSchema(
                feature_set_version="features.unit.v1",
                feature_names=("close_location",),
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
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        '{"metadata": {}, "model_metadata": {"primary_strategy": "unit"}, '
        '"strategies": {"unit": {"metrics": {}}, "rule_only_oos": {"metrics": {}}}}'
    )
    stability_path = tmp_path / "stability.json"
    stability_path.write_text('{"stability_report": {"status": "pass"}}')
    experiment_path = tmp_path / "experiment.json"
    experiment_path.write_text('{"experiment_name": "unit"}')
    pack_config = PaperTradingPackConfig.from_dict(
        {
            "pack_name": "unit_pack",
            "output_path": str(tmp_path / "pack.json"),
            "issue_id": "CT-132",
            "epic_id": "CT-113",
            "candidate_name": "unit_candidate",
            "plan_path": "docs/unit.md",
            "source_artifacts": {
                "model_artifact_path": str(model_path),
                "baseline_report_path": str(baseline_path),
                "stability_report_path": str(stability_path),
                "experiment_config_path": str(experiment_path),
            },
            "strategy": {
                "side": "long",
                "symbols": ["TONUSDT", "BTCUSDT", "ETHUSDT"],
                "filters": [{"feature": "close_location", "operator": ">=", "value": 0.0}],
                "ranking": {"top_n_per_decision_time": 1, "selected_expected_r_threshold": -1.0},
                "exits": {"stop_loss_pct": 0.004, "target_pct": 0.008, "horizon_bars": 12},
            },
            "paper_gate": {"minimum_calendar_days": 30, "minimum_paper_trades": 100},
            "monitoring": {},
            "reconciliation": {},
        }
    )
    build_paper_trading_pack(pack_config)
    return pack_config.output_path


def _fake_klines(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    limit: int,
    base_url: str,
) -> list[list[object]]:
    rows = []
    current = start_time
    price = 10.0 if symbol == "TONUSDT" else 100.0
    while current < end_time:
        close = price + (current.minute % 5) * 0.01
        rows.append(
            [
                int(current.timestamp() * 1000),
                str(close - 0.01),
                str(close + 0.02),
                str(close - 0.02),
                str(close),
                "100",
                int((current + timedelta(minutes=1)).timestamp() * 1000) - 1,
                "1000",
                20,
                "55",
                "550",
                "0",
            ]
        )
        current += timedelta(minutes=1)
    return rows[:limit]


def _fake_funding(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    limit: int,
    base_url: str,
) -> list[dict[str, object]]:
    rows = []
    current = start_time
    rates = [-0.00001, -0.00002, -0.00008]
    index = 0
    while current <= end_time:
        rows.append(
            {
                "symbol": symbol,
                "fundingTime": int(current.timestamp() * 1000),
                "fundingRate": str(rates[index % len(rates)]),
                "markPrice": "10",
            }
        )
        current += timedelta(hours=8)
        index += 1
    return rows[-limit:]
