from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

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


def test_config_parses_accepted_sessions(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    dataset_manifest.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest.write_text('{"funding": "unit"}', encoding="utf-8")

    config = HistoricalHoldoutReplayConfig.from_dict(
        {
            "run_name": "unit_replay",
            "output_dir": str(tmp_path / "out"),
            "issue_id": "CT-174",
            "epic_id": "CT-113",
            "dataset_manifest_path": str(dataset_manifest),
            "funding_manifest_path": str(funding_manifest),
            "pack_manifest_paths": [],
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "accepted_sessions": ["Europe"],
            "generated_at": "2026-05-27T16:00:00Z",
        }
    )

    assert config.accepted_sessions == ("europe",)


def test_trade_session_filter_keeps_requested_sessions(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    dataset_manifest.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest.write_text('{"funding": "unit"}', encoding="utf-8")
    config = HistoricalHoldoutReplayConfig.from_dict(
        {
            "run_name": "unit_replay",
            "output_dir": str(tmp_path / "out"),
            "issue_id": "CT-174",
            "epic_id": "CT-113",
            "dataset_manifest_path": str(dataset_manifest),
            "funding_manifest_path": str(funding_manifest),
            "pack_manifest_paths": [],
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "accepted_sessions": ["europe"],
            "generated_at": "2026-05-27T16:00:00Z",
        }
    )

    rows = [
        {"decision_time": "2026-01-01T07:59:00Z", "symbol": "SOLUSDT"},
        {"decision_time": "2026-01-01T08:00:00Z", "symbol": "SUIUSDT"},
        {"decision_time": "2026-01-01T15:59:00Z", "symbol": "AVAXUSDT"},
        {"decision_time": "2026-01-01T16:00:00Z", "symbol": "ADAUSDT"},
    ]

    filtered = replay_module._apply_trade_filters(rows, config)

    assert [row["symbol"] for row in filtered] == ["SUIUSDT", "AVAXUSDT"]


def test_abstention_filters_skip_only_full_pattern_matches(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    dataset_manifest.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest.write_text('{"funding": "unit"}', encoding="utf-8")
    config = HistoricalHoldoutReplayConfig.from_dict(
        {
            "run_name": "unit_replay",
            "output_dir": str(tmp_path / "out"),
            "issue_id": "CT-175",
            "epic_id": "CT-113",
            "dataset_manifest_path": str(dataset_manifest),
            "funding_manifest_path": str(funding_manifest),
            "pack_manifest_paths": [],
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "abstention_filters": [
                {
                    "feature": "eth_trend_above_ma_20",
                    "operator": "<=",
                    "value": 0,
                },
                {
                    "feature": "mtf_15m_market_positive_return_fraction",
                    "operator": "<",
                    "value": 0.5,
                },
            ],
            "generated_at": "2026-05-27T16:00:00Z",
        }
    )

    rows = [
        {
            "symbol": "SOLUSDT",
            "eth_trend_above_ma_20": 0,
            "mtf_15m_market_positive_return_fraction": 0.25,
        },
        {
            "symbol": "SUIUSDT",
            "eth_trend_above_ma_20": 0,
            "mtf_15m_market_positive_return_fraction": 0.75,
        },
        {
            "symbol": "AVAXUSDT",
            "eth_trend_above_ma_20": 1,
            "mtf_15m_market_positive_return_fraction": 0.25,
        },
    ]

    filtered = replay_module._apply_trade_filters(rows, config)

    assert [row["symbol"] for row in filtered] == ["SUIUSDT", "AVAXUSDT"]


def test_abstention_filter_groups_skip_any_matching_pattern(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    dataset_manifest.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest.write_text('{"funding": "unit"}', encoding="utf-8")
    config = HistoricalHoldoutReplayConfig.from_dict(
        {
            "run_name": "unit_replay",
            "output_dir": str(tmp_path / "out"),
            "issue_id": "CT-180",
            "epic_id": "CT-113",
            "dataset_manifest_path": str(dataset_manifest),
            "funding_manifest_path": str(funding_manifest),
            "pack_manifest_paths": [],
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "abstention_filter_groups": [
                [
                    {
                        "feature": "fm_oi_value_change_1h",
                        "operator": ">",
                        "value": 0.015,
                    }
                ],
                [
                    {
                        "feature": "fm_session_europe",
                        "operator": ">=",
                        "value": 1,
                    }
                ],
            ],
            "generated_at": "2026-05-27T16:00:00Z",
        }
    )

    rows = [
        {"symbol": "SOLUSDT", "fm_oi_value_change_1h": 0.02, "fm_session_europe": 0},
        {"symbol": "SUIUSDT", "fm_oi_value_change_1h": 0.0, "fm_session_europe": 1},
        {"symbol": "AVAXUSDT", "fm_oi_value_change_1h": 0.0, "fm_session_europe": 0},
    ]

    filtered = replay_module._apply_trade_filters(rows, config)

    assert [row["symbol"] for row in filtered] == ["AVAXUSDT"]


def test_external_feature_rows_join_before_abstention_filters(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    external_features_path = tmp_path / "external_features.parquet"
    dataset_manifest.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest.write_text('{"funding": "unit"}', encoding="utf-8")
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "symbol": "SOLUSDT",
                    "timeframe": "h12",
                    "decision_time": datetime(2026, 1, 1, 8, tzinfo=UTC),
                    "fm_oi_value_change_1h": 0.02,
                    "fm_metrics_match": 1,
                },
                {
                    "symbol": "SUIUSDT",
                    "timeframe": "h12",
                    "decision_time": datetime(2026, 1, 1, 8, tzinfo=UTC),
                    "fm_oi_value_change_1h": 0.01,
                    "fm_metrics_match": 1,
                },
            ]
        ),
        external_features_path,
    )
    config = HistoricalHoldoutReplayConfig.from_dict(
        {
            "run_name": "unit_replay",
            "output_dir": str(tmp_path / "out"),
            "issue_id": "CT-179",
            "epic_id": "CT-113",
            "dataset_manifest_path": str(dataset_manifest),
            "funding_manifest_path": str(funding_manifest),
            "pack_manifest_paths": [],
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "external_feature_rows_path": str(external_features_path),
            "abstention_filters": [
                {
                    "feature": "fm_oi_value_change_1h",
                    "operator": ">",
                    "value": 0.015,
                }
            ],
            "generated_at": "2026-05-27T16:00:00Z",
        }
    )

    rows = [
        {
            "symbol": "SOLUSDT",
            "timeframe": "h12",
            "decision_time": datetime(2026, 1, 1, 8, tzinfo=UTC),
        },
        {
            "symbol": "SUIUSDT",
            "timeframe": "h12",
            "decision_time": datetime(2026, 1, 1, 8, tzinfo=UTC),
        },
    ]

    joined = replay_module._join_external_feature_rows(rows, config)
    filtered = replay_module._apply_trade_filters(joined, config)

    assert [row["symbol"] for row in filtered] == ["SUIUSDT"]
    assert filtered[0]["fm_oi_value_change_1h"] == 0.01


def test_external_feature_abstention_filter_requires_feature_rows_path(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    dataset_manifest.write_text('{"dataset": "unit"}', encoding="utf-8")
    funding_manifest.write_text('{"funding": "unit"}', encoding="utf-8")
    config = HistoricalHoldoutReplayConfig.from_dict(
        {
            "run_name": "unit_replay",
            "output_dir": str(tmp_path / "out"),
            "issue_id": "CT-179",
            "epic_id": "CT-113",
            "dataset_manifest_path": str(dataset_manifest),
            "funding_manifest_path": str(funding_manifest),
            "pack_manifest_paths": [],
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "abstention_filters": [
                {
                    "feature": "fm_oi_value_change_1h",
                    "operator": ">",
                    "value": 0.015,
                }
            ],
            "generated_at": "2026-05-27T16:00:00Z",
        }
    )

    with pytest.raises(ValueError, match="external_feature_rows_path is required"):
        replay_module._join_external_feature_rows(
            [
                {
                    "symbol": "SOLUSDT",
                    "timeframe": "h12",
                    "decision_time": datetime(2026, 1, 1, 8, tzinfo=UTC),
                }
            ],
            config,
        )


def test_run_historical_holdout_replay_uses_pack_replay_cache_without_loading_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset_manifest = tmp_path / "dataset_manifest.json"
    funding_manifest = tmp_path / "funding_manifest.json"
    pack_manifest = tmp_path / "pack.json"
    dataset_manifest.write_text('{"row_count": 10}', encoding="utf-8")
    funding_manifest.write_text('{"row_count": 2}', encoding="utf-8")
    pack_manifest.write_text('{"pack_name": "unit_pack"}', encoding="utf-8")
    config = HistoricalHoldoutReplayConfig.from_dict(
        {
            "run_name": "unit_replay",
            "output_dir": str(tmp_path / "out"),
            "feature_cache_dir": str(tmp_path / "feature_cache"),
            "replay_cache_dir": str(tmp_path / "replay_cache"),
            "issue_id": "CT-171",
            "epic_id": "CT-113",
            "dataset_manifest_path": str(dataset_manifest),
            "funding_manifest_path": str(funding_manifest),
            "pack_manifest_paths": [str(pack_manifest)],
            "feature": {
                "feature_set_version": "features.unit.v1",
                "rolling_window": 3,
                "higher_timeframes": ["5m"],
            },
            "generated_at": "2026-05-27T16:00:00Z",
        }
    )
    feature_cache_key = replay_module._feature_cache_key(config)
    rows_path, manifest_path = replay_module._feature_cache_paths(config, feature_cache_key)
    replay_module._write_feature_cache(
        feature_cache_key,
        rows_path,
        manifest_path,
        config,
        FeatureFrame(
            rows=[{"decision_time": datetime(2026, 1, 1, tzinfo=UTC), "close_location": 0.6}],
            manifest=FeatureManifest(
                schema_version="research.dataset.v1",
                feature_set_version=config.feature_set_version,
                generator_name="unit",
                row_count=1,
                features=(),
            ),
        ),
    )
    replay = {
        "pack_manifest_path": str(pack_manifest),
        "pack_name": "unit_pack",
        "candidate_name": "unit_candidate",
        "metrics": {
            "trade_count": 3,
            "average_r": 0.2,
            "max_drawdown_pct": 0.01,
            "profit_factor": 1.5,
        },
        "trades_path": "unit_pack/selected_trades.parquet",
        "accepted_trades_path": "unit_pack/accepted_trades.parquet",
        "trades": [],
        "accepted_trades": [],
    }
    replay_module._write_pack_replay_cache(config, pack_manifest, feature_cache_key, replay)

    def fail_read_rows(_):
        raise AssertionError("fast replay cache path should not load full parquet rows")

    monkeypatch.setattr(replay_module, "_read_manifest_rows", fail_read_rows)

    payload = replay_module.run_historical_holdout_replay(config)

    assert payload["replay_cache"]["status"] == "hit"
    assert payload["feature_cache"]["status"] == "hit"
    assert payload["row_counts"]["source_rows"] == 10
    assert payload["row_counts"]["funding_rows"] == 2
    assert payload["row_counts"]["feature_rows"] == 1
    assert payload["replays"][0]["candidate_name"] == "unit_candidate"
    assert (config.output_dir / "replay_report.json").exists()
