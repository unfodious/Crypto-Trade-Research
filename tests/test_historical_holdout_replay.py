from datetime import UTC, datetime
from pathlib import Path

import crypto_trade_research.historical_holdout_replay as replay_module
from crypto_trade_research.features import (
    FeatureConfig,
    FeatureFrame,
    FeatureManifest,
    FeatureSpec,
)
from crypto_trade_research.historical_holdout_replay import HistoricalHoldoutReplayConfig


def test_feature_cache_reuses_matching_holdout_features(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    dataset_manifest.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest.write_text('{"funding": "unit"}', encoding="utf-8")
    config = HistoricalHoldoutReplayConfig.from_dict(
        {
            "run_name": "unit_replay",
            "output_dir": str(tmp_path / "out"),
            "feature_cache_dir": str(tmp_path / "cache"),
            "issue_id": "CT-170",
            "epic_id": "CT-113",
            "dataset_manifest_path": str(dataset_manifest),
            "funding_manifest_path": str(funding_manifest),
            "pack_manifest_paths": [],
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "generated_at": "2026-05-27T16:00:00Z",
        }
    )
    calls = 0

    def fake_generate(
        source_rows,
        feature_config,
        *,
        funding_rate_rows,
    ) -> FeatureFrame:
        nonlocal calls
        calls += 1
        return FeatureFrame(
            rows=[
                {
                    "venue": "binance",
                    "market_type": "um_futures",
                    "symbol": "SOLUSDT",
                    "timeframe": "1m",
                    "decision_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "source_available_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "close_location": 0.6,
                }
            ],
            manifest=FeatureManifest(
                schema_version="research.dataset.v1",
                feature_set_version=feature_config.feature_set_version,
                generator_name="unit",
                row_count=1,
                features=(
                    FeatureSpec(
                        "close_location",
                        "indicator",
                        1,
                        "post_close",
                        "Unit feature.",
                    ),
                ),
            ),
        )

    monkeypatch.setattr(replay_module, "generate_ohlcv_features", fake_generate)
    feature_config = FeatureConfig(
        feature_set_version=config.feature_set_version,
        rolling_window=config.rolling_window,
        higher_timeframes=config.higher_timeframes,
    )

    first_features, first_cache = replay_module._load_or_build_features(
        config,
        source_rows=[{"symbol": "SOLUSDT"}],
        funding_rows=[],
        feature_config=feature_config,
    )
    second_features, second_cache = replay_module._load_or_build_features(
        config,
        source_rows=[{"symbol": "SOLUSDT"}],
        funding_rows=[],
        feature_config=feature_config,
    )

    assert calls == 1
    assert first_cache["status"] == "miss"
    assert second_cache["status"] == "hit"
    assert second_features.rows == first_features.rows
    assert Path(str(second_cache["rows_path"])).exists()


def test_feature_cache_key_changes_with_feature_parameters(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    dataset_manifest.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest.write_text('{"funding": "unit"}', encoding="utf-8")
    base = {
        "run_name": "unit_replay",
        "output_dir": str(tmp_path / "out"),
        "feature_cache_dir": str(tmp_path / "cache"),
        "issue_id": "CT-170",
        "epic_id": "CT-113",
        "dataset_manifest_path": str(dataset_manifest),
        "funding_manifest_path": str(funding_manifest),
        "pack_manifest_paths": [],
        "feature": {
            "feature_set_version": "features.unit.v1",
            "rolling_window": 3,
            "higher_timeframes": ["5m"],
        },
        "generated_at": "2026-05-27T16:00:00Z",
    }
    changed = dict(base)
    changed["feature"] = {
        "feature_set_version": "features.unit.v1",
        "rolling_window": 4,
        "higher_timeframes": ["5m"],
    }

    base_config = HistoricalHoldoutReplayConfig.from_dict(base)
    changed_config = HistoricalHoldoutReplayConfig.from_dict(changed)

    assert replay_module._feature_cache_key(base_config) != replay_module._feature_cache_key(
        changed_config
    )
