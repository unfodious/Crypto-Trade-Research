import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.timeframe_continuation_scan import (
    TimeframeContinuationScanConfig,
    build_timeframe_continuation_scan_report,
)


def test_timeframe_continuation_scan_filters_joined_features(tmp_path: Path) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            _trade_row("2026-01-01T00:00:00Z", "SOLUSDT", 2.0, 4.0, -0.5),
            _trade_row("2026-01-01T01:00:00Z", "SOLUSDT", -1.0, 0.5, -1.1),
        ],
        [
            _feature_row("2026-01-01T00:00:00Z", "SOLUSDT", 1.0),
            _feature_row("2026-01-01T01:00:00Z", "SOLUSDT", 0.0),
        ],
    )

    payload = build_timeframe_continuation_scan_report(
        TimeframeContinuationScanConfig.from_dict(
            {
                "report_name": "unit_timeframe",
                "issue_id": "CT-188",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "target_runner_r": 3,
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [
                    {
                        "name": "core3_base",
                        "max_trades_per_day": 10,
                        "allowed_symbols": ["SOLUSDT"],
                    },
                    {
                        "name": "trend_only",
                        "max_trades_per_day": 10,
                        "allowed_symbols": ["SOLUSDT"],
                        "feature_filters": [
                            {
                                "feature": "mtf_15m_trend_above_ma_20",
                                "operator": ">=",
                                "value": 1,
                            }
                        ],
                    },
                ],
            }
        )
    )

    baseline, trend = payload["scenarios"]
    assert baseline["accepted_trade_count"] == 2
    assert trend["accepted_trade_count"] == 1
    assert trend["average_r"] == 2.0
    assert trend["clean_runner_share"] == 1.0
    assert (tmp_path / "out" / "report.md").exists()


def test_timeframe_continuation_scan_applies_daily_cap_before_filters(tmp_path: Path) -> None:
    replay_report_path = _write_replay(
        tmp_path,
        [
            _trade_row("2026-01-01T00:00:00Z", "SOLUSDT", 1.0, 3.0, -0.5),
            _trade_row("2026-01-01T01:00:00Z", "SOLUSDT", 1.0, 3.0, -0.5),
        ],
        [
            _feature_row("2026-01-01T00:00:00Z", "SOLUSDT", 1.0),
            _feature_row("2026-01-01T01:00:00Z", "SOLUSDT", 1.0),
        ],
    )

    payload = build_timeframe_continuation_scan_report(
        TimeframeContinuationScanConfig.from_dict(
            {
                "report_name": "unit_timeframe",
                "issue_id": "CT-188",
                "epic_id": "CT-113",
                "output_json_path": str(tmp_path / "out" / "report.json"),
                "output_markdown_path": str(tmp_path / "out" / "report.md"),
                "windows": [{"name": "unit", "replay_report_path": str(replay_report_path)}],
                "scenarios": [
                    {
                        "name": "core3_base",
                        "max_trades_per_day": 1,
                        "allowed_symbols": ["SOLUSDT"],
                    }
                ],
            }
        )
    )

    assert payload["scenarios"][0]["accepted_trade_count"] == 1


def _trade_row(
    decision_time: str,
    symbol: str,
    realized_r: float,
    mfe: float,
    mae: float,
) -> dict[str, object]:
    return {
        "decision_time": decision_time,
        "exit_time": decision_time,
        "symbol": symbol,
        "timeframe": "1m",
        "expected_r": 0.5,
        "target_before_stop_probability": 0.6,
        "rank": 1,
        "realized_r_after_costs": realized_r,
        "max_favorable_excursion_r": mfe,
        "max_adverse_excursion_r": mae,
    }


def _feature_row(
    decision_time: str,
    symbol: str,
    trend: float,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timeframe": "1m",
        "decision_time": datetime.fromisoformat(decision_time.replace("Z", "+00:00")).astimezone(
            UTC
        ),
        "mtf_15m_trend_above_ma_20": trend,
    }


def _write_replay(
    tmp_path: Path,
    selected_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
) -> Path:
    replay_dir = tmp_path / "replay"
    selected_path = replay_dir / "pack" / "selected_trades.parquet"
    feature_path = replay_dir / "features.parquet"
    pack_manifest_path = tmp_path / "pack_manifest.json"
    _write_table(selected_path, selected_rows)
    _write_table(feature_path, feature_rows)
    _write_json(
        pack_manifest_path,
        {
            "strategy": {
                "risk_controls": {
                    "max_trades_per_decision_time": 3,
                    "max_trades_per_symbol": 600,
                    "loss_cooldown_signals": 0,
                }
            }
        },
    )
    replay_report_path = replay_dir / "replay_report.json"
    _write_json(
        replay_report_path,
        {
            "feature_cache": {"rows_path": str(feature_path)},
            "replays": [
                {
                    "pack_manifest_path": str(pack_manifest_path),
                    "trades_path": "pack/selected_trades.parquet",
                }
            ],
        },
    )
    return replay_report_path


def _write_table(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
