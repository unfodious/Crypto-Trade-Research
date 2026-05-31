import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_trade_research.forward_skip_counterfactual import (
    SkipCounterfactualConfig,
    build_forward_skip_counterfactual_report,
)


def test_forward_skip_counterfactual_replays_expected_r_skips(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    signals_path = _write_signals(tmp_path)
    config = SkipCounterfactualConfig.from_dict(
        {
            "report_name": "unit_skip_counterfactual",
            "issue_id": "CT-199",
            "epic_id": "CT-113",
            "output_json_path": str(tmp_path / "report.json"),
            "output_markdown_path": str(tmp_path / "report.md"),
            "request_sleep_seconds": 0,
            "streams": [
                {
                    "name": "unit_forward",
                    "issue_id": "CT-146",
                    "forward_signals_path": str(signals_path),
                    "pack_manifest_path": str(pack_path),
                }
            ],
        }
    )

    report = build_forward_skip_counterfactual_report(config, fetch_klines=_fake_klines)

    assert report["schema_version"] == "research.forward-skip-counterfactual.v1"
    assert report["decision"]["live_trading_approved"] is False
    assert report["decision"]["working_model"] is False
    assert report["aggregate"]["signal_count"] == 1
    assert report["aggregate"]["closed_trade_count"] == 1
    assert report["aggregate"]["average_r_after_costs"] == pytest.approx(1.825)
    assert report["aggregate"]["exit_reasons"] == {"target": 1}
    assert (tmp_path / "report.json").exists()
    assert "Research-only skipped-signal counterfactual" in (tmp_path / "report.md").read_text(
        encoding="utf-8"
    )


def test_ct199_committed_config_points_at_all_forward_streams() -> None:
    config = SkipCounterfactualConfig.from_path(
        Path("configs/ct199-forward-skip-counterfactual.json")
    )

    stream_names = {stream.name for stream in config.streams}

    assert stream_names == {
        "ct145_no_ton_negative_funding_forward_paper",
        "ct156_high_beta_dot_shadow_forward_paper",
        "ct184_adaptive_sizing_shadow_forward_paper",
    }


def _write_pack(tmp_path: Path) -> Path:
    path = tmp_path / "pack_manifest.json"
    path.write_text(
        json.dumps(
            {
                "strategy": {
                    "side": "long",
                    "exits": {
                        "stop_loss_pct": 0.004,
                        "target_pct": 0.008,
                        "horizon_bars": 12,
                        "target_stop_tie_breaker": "stop_first",
                    },
                    "cost_model": {"round_trip_cost_pct": 0.0007},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_signals(tmp_path: Path) -> Path:
    path = tmp_path / "forward_signals.json"
    path.write_text(
        json.dumps(
            {
                "signals": [
                    {
                        "request_id": "unit:2026-05-27T00:00:00Z:SOLUSDT",
                        "symbol": "SOLUSDT",
                        "timeframe": "1m",
                        "signal_timestamp": "2026-05-27T00:00:00Z",
                        "model_id": "unit",
                        "model_version": "20260527T000000Z",
                        "artifact_hash": "hash",
                        "expected_r": -0.3,
                        "target_before_stop_probability": 0.55,
                        "rank": 1,
                        "feature_freshness_seconds": 0.0,
                        "funding_source_latency_seconds": 0.0,
                        "entry_price": 100.0,
                        "stop_price": 99.6,
                        "target_price": 100.8,
                        "recommended_action": "skip",
                        "reason_codes": ["expected_r_below_threshold"],
                        "hard_risk_blocks": ["expected_r_or_rank_block"],
                    },
                    {
                        "request_id": "unit:2026-05-27T00:00:00Z:BTCUSDT",
                        "symbol": "BTCUSDT",
                        "timeframe": "1m",
                        "signal_timestamp": "2026-05-27T00:00:00Z",
                        "entry_price": 100.0,
                        "stop_price": 99.6,
                        "target_price": 100.8,
                        "recommended_action": "take",
                        "reason_codes": ["expected_r_above_threshold"],
                        "hard_risk_blocks": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _fake_klines(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    limit: int,
    base_url: str,
) -> list[list[object]]:
    assert symbol == "SOLUSDT"
    assert limit == 1500
    assert base_url
    rows = []
    current = start_time.astimezone(UTC)
    for offset in range(3):
        open_time = current + timedelta(minutes=offset)
        rows.append(
            [
                int(open_time.timestamp() * 1000),
                "100.0",
                "100.9",
                "99.9",
                "100.5",
                "1",
                int((open_time + timedelta(minutes=1)).timestamp() * 1000) - 1,
                "100",
                10,
                "0.5",
                "50",
                "0",
            ]
        )
    return rows
