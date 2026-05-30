import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.selected_trade_abstention import (
    AbstentionRule,
    AbstentionWindowConfig,
    SelectedTradeAbstentionConfig,
    build_selected_trade_abstention_report,
)


def test_selected_trade_abstention_recomputes_metrics_after_skips(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.json"
    replay_dir = tmp_path / "replay"
    replay_report_path = replay_dir / "replay_report.json"
    selected_path = replay_dir / "unit_pack" / "selected_trades.parquet"
    feature_rows_path = tmp_path / "features.parquet"
    _write_json(
        pack_path,
        {
            "strategy": {
                "side": "long",
                "risk_controls": {
                    "max_trades_per_symbol": None,
                    "max_trades_per_decision_time": None,
                    "loss_cooldown_signals": 0,
                },
            }
        },
    )
    _write_json(
        replay_report_path,
        {
            "replays": [
                {
                    "candidate_name": "unit_candidate",
                    "pack_manifest_path": str(pack_path),
                    "trades_path": "unit_pack/selected_trades.parquet",
                    "metrics": {"trade_count": 2, "average_r": 0.0},
                }
            ]
        },
    )
    _write_table(
        selected_path,
        [
            {
                "decision_time": "2026-01-01T00:00:00Z",
                "symbol": "SOLUSDT",
                "timeframe": "1m",
                "expected_r": 0.5,
                "realized_r_after_costs": -1.0,
                "exit_time": "2026-01-01T00:10:00Z",
            },
            {
                "decision_time": "2026-01-01T00:01:00Z",
                "symbol": "SUIUSDT",
                "timeframe": "1m",
                "expected_r": 0.5,
                "realized_r_after_costs": 1.0,
                "exit_time": "2026-01-01T00:11:00Z",
            },
        ],
    )
    _write_table(
        feature_rows_path,
        [
            {
                "symbol": "SOLUSDT",
                "timeframe": "1m",
                "decision_time": datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                "mtf_15m_eth_return_1": -0.01,
                "mtf_15m_market_positive_return_fraction": 0.25,
            },
            {
                "symbol": "SUIUSDT",
                "timeframe": "1m",
                "decision_time": datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
                "mtf_15m_eth_return_1": -0.01,
                "mtf_15m_market_positive_return_fraction": 0.75,
            },
        ],
    )

    report = build_selected_trade_abstention_report(
        SelectedTradeAbstentionConfig(
            report_name="unit_abstention",
            issue_id="CT-176",
            epic_id="CT-113",
            output_json_path=tmp_path / "out" / "report.json",
            output_markdown_path=tmp_path / "out" / "report.md",
            windows=(
                AbstentionWindowConfig(
                    name="unit_window",
                    replay_report_path=replay_report_path,
                    feature_rows_path=feature_rows_path,
                ),
            ),
            rules=(
                AbstentionRule(
                    name="eth_down_breadth_weak",
                    filters=(
                        {
                            "feature": "mtf_15m_eth_return_1",
                            "operator": "<",
                            "value": 0,
                        },
                        {
                            "feature": "mtf_15m_market_positive_return_fraction",
                            "operator": "<",
                            "value": 0.5,
                        },
                    ),
                ),
            ),
        )
    )

    candidate = report["windows"][0]["candidates"][0]
    assert candidate["matched_feature_count"] == 2
    base_rule, abstention_rule = candidate["rules"]
    assert base_rule["metrics"]["trade_count"] == 2
    assert base_rule["metrics"]["average_r"] == 0.0
    assert abstention_rule["skipped_row_count"] == 1
    assert abstention_rule["metrics"]["trade_count"] == 1
    assert abstention_rule["metrics"]["average_r"] == 1.0
    assert (tmp_path / "out" / "report.json").exists()
    assert "eth_down_breadth_weak" in (tmp_path / "out" / "report.md").read_text(encoding="utf-8")


def test_selected_trade_abstention_supports_filter_groups_or_logic(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.json"
    replay_dir = tmp_path / "replay"
    replay_report_path = replay_dir / "replay_report.json"
    selected_path = replay_dir / "unit_pack" / "selected_trades.parquet"
    feature_rows_path = tmp_path / "features.parquet"
    _write_json(
        pack_path,
        {
            "strategy": {
                "side": "long",
                "risk_controls": {
                    "max_trades_per_symbol": None,
                    "max_trades_per_decision_time": None,
                    "loss_cooldown_signals": 0,
                },
            }
        },
    )
    _write_json(
        replay_report_path,
        {
            "replays": [
                {
                    "candidate_name": "unit_candidate",
                    "pack_manifest_path": str(pack_path),
                    "trades_path": "unit_pack/selected_trades.parquet",
                    "metrics": {"trade_count": 3, "average_r": 0.0},
                }
            ]
        },
    )
    _write_table(
        selected_path,
        [
            {
                "decision_time": "2026-01-01T07:00:00Z",
                "symbol": "SOLUSDT",
                "timeframe": "1m",
                "expected_r": 0.5,
                "realized_r_after_costs": -1.0,
                "exit_time": "2026-01-01T07:10:00Z",
            },
            {
                "decision_time": "2026-01-01T09:00:00Z",
                "symbol": "SUIUSDT",
                "timeframe": "1m",
                "expected_r": 0.5,
                "realized_r_after_costs": -0.5,
                "exit_time": "2026-01-01T09:10:00Z",
            },
            {
                "decision_time": "2026-01-01T17:00:00Z",
                "symbol": "AVAXUSDT",
                "timeframe": "1m",
                "expected_r": 0.5,
                "realized_r_after_costs": 1.0,
                "exit_time": "2026-01-01T17:10:00Z",
            },
        ],
    )
    _write_table(
        feature_rows_path,
        [
            {
                "symbol": "SOLUSDT",
                "timeframe": "1m",
                "decision_time": datetime(2026, 1, 1, 7, tzinfo=UTC),
                "fm_oi_value_change_1h": 0.02,
                "fm_session_europe": 0,
            },
            {
                "symbol": "SUIUSDT",
                "timeframe": "1m",
                "decision_time": datetime(2026, 1, 1, 9, tzinfo=UTC),
                "fm_oi_value_change_1h": 0.0,
                "fm_session_europe": 1,
            },
            {
                "symbol": "AVAXUSDT",
                "timeframe": "1m",
                "decision_time": datetime(2026, 1, 1, 17, tzinfo=UTC),
                "fm_oi_value_change_1h": 0.0,
                "fm_session_europe": 0,
            },
        ],
    )

    report = build_selected_trade_abstention_report(
        SelectedTradeAbstentionConfig.from_dict(
            {
                "report_name": "unit_abstention",
                "issue_id": "CT-180",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "windows": [
                    {
                        "name": "unit_window",
                        "replay_report_path": str(replay_report_path),
                        "feature_rows_path": str(feature_rows_path),
                    }
                ],
                "rules": [
                    {
                        "name": "oi_high_or_europe",
                        "filter_groups": [
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
                    }
                ],
            }
        )
    )

    rule = report["windows"][0]["candidates"][0]["rules"][1]
    assert rule["skipped_row_count"] == 2
    assert rule["metrics"]["trade_count"] == 1
    assert rule["metrics"]["average_r"] == 1.0
    assert rule["symbol_metrics"] == [
        {"symbol": "AVAXUSDT", "trade_count": 1, "average_r": 1.0, "positive": True}
    ]
    assert rule["session_metrics"] == [
        {"session": "us", "trade_count": 1, "average_r": 1.0, "positive": True}
    ]


def _write_table(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
