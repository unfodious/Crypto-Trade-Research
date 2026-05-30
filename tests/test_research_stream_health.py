import json
from pathlib import Path

from crypto_trade_research.research_stream_health import build_research_stream_health_report


def test_build_research_stream_health_report_summarizes_active_streams(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data/generated/ct145_no_ton_negative_funding_forward_paper/forward_run.json",
        {
            "collector_summary": {
                "decision_time": "2026-05-27T11:00:00Z",
                "candidate_count": 0,
                "signal_count": 0,
                "take_count": 0,
            },
            "row_counts": {"closed_trades": 0, "open_trades": 0, "cumulative_trades": 0},
        },
    )
    _write_json(
        tmp_path
        / "data/generated/ct145_no_ton_negative_funding_forward_paper/monitoring_report.json",
        {
            "monitoring_status": "gate_failed",
            "decision": {"working_model": False, "live_trading_approved": False},
            "metrics": {
                "trade_count": 0,
                "open_trade_count": 0,
                "average_r_after_costs": 0.0,
                "max_drawdown_pct": 0.0,
                "reached_1_0r_then_lost_count": 0,
                "counterfactual_exit_metrics": {},
            },
            "warnings": [],
        },
    )
    _write_json(
        tmp_path / "data/generated/ct156_high_beta_dot_shadow_forward_paper/forward_run.json",
        {
            "collector_summary": {
                "decision_time": "2026-05-27T11:00:00Z",
                "candidate_count": 0,
                "signal_count": 0,
                "take_count": 0,
            },
            "row_counts": {"closed_trades": 0, "open_trades": 0, "cumulative_trades": 0},
        },
    )
    _write_json(
        tmp_path / "data/generated/ct156_high_beta_dot_shadow_forward_paper/monitoring_report.json",
        {
            "monitoring_status": "gate_failed",
            "decision": {"working_model": False, "live_trading_approved": False},
            "metrics": {
                "trade_count": 0,
                "open_trade_count": 0,
                "average_r_after_costs": 0.0,
                "max_drawdown_pct": 0.0,
                "reached_1_0r_then_lost_count": 0,
                "counterfactual_exit_metrics": {},
            },
            "warnings": [],
        },
    )
    _write_json(
        tmp_path / "data/generated/ct180_oi_europe_shadow_forward_paper/forward_run.json",
        {
            "collector_summary": {
                "decision_time": "2026-05-27T11:00:00Z",
                "candidate_count": 0,
                "signal_count": 0,
                "take_count": 0,
            },
            "row_counts": {
                "closed_trades": 0,
                "open_trades": 0,
                "cumulative_trades": 0,
                "futures_metrics": 396,
            },
        },
    )
    _write_json(
        tmp_path / "data/generated/ct180_oi_europe_shadow_forward_paper/monitoring_report.json",
        {
            "monitoring_status": "gate_failed",
            "decision": {"working_model": False, "live_trading_approved": False},
            "metrics": {
                "trade_count": 0,
                "open_trade_count": 0,
                "average_r_after_costs": 0.0,
                "max_drawdown_pct": 0.0,
                "reached_1_0r_then_lost_count": 0,
                "counterfactual_exit_metrics": {},
            },
            "warnings": [],
        },
    )
    _write_json(
        tmp_path / "data/generated/ct134_hyperliquid_whale_watchlist/watchlist_run.json",
        {
            "created_at": "2026-05-27T10:57:34Z",
            "alert_count": 0,
            "alerts": [],
            "snapshots": [
                {
                    "generated_at": "2026-05-27T10:57:33Z",
                    "position_count": 0,
                    "fill_count": 0,
                    "alert_count": 0,
                    "warning_count": 0,
                    "warnings": [],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "data/generated/ct151_binance_crowding_forward/crowding_run.json",
        {
            "latest_generated_at": "2026-05-27T10:58:20Z",
            "generator_version": "ct153.binance_crowding_forward.v2",
            "row_count": 55,
            "period": "5m",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "warnings": [],
        },
    )
    _write_json(
        tmp_path / "data/generated/ct158_binance_order_book_forward/order_book_run.json",
        {
            "latest_generated_at": "2026-05-27T10:59:20Z",
            "generator_version": "ct158.binance_order_book_forward.v1",
            "row_count": 451,
            "summary_row_count": 11,
            "level_row_count": 440,
            "depth_limit": 20,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "warnings": [],
        },
    )
    _write_json(
        tmp_path / "data/generated/ct160_binance_liquidations_forward/liquidation_run.json",
        {
            "latest_generated_at": "2026-05-27T11:01:20Z",
            "capture_started_at": "2026-05-27T11:01:20Z",
            "capture_ended_at": "2026-05-27T11:02:30Z",
            "generator_version": "ct160.binance_liquidations_forward.v1",
            "row_count": 0,
            "event_count_total": 0,
            "event_count_filtered_out": 0,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "warnings": [],
        },
    )
    _write_json(
        tmp_path
        / "data/generated/ct162_external_forward_features/external_forward_features_run.json",
        {
            "latest_generated_at": "2026-05-27T11:05:20Z",
            "generator_version": "ct162.external_forward_features.v1",
            "row_count": 44,
            "crowding_snapshot_count": 2,
            "order_book_snapshot_count": 1,
            "liquidation_snapshot_count": 1,
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "warnings": [],
        },
    )
    _write_json(
        tmp_path / "data/generated/ct164_external_forward_evidence_readiness/readiness_report.json",
        {
            "created_at": "2026-05-27T11:10:20Z",
            "readiness_status": "not_ready",
            "decision": {
                "ready_for_external_validation_matrix": False,
                "working_model": False,
                "live_trading_approved": False,
            },
            "external_features": {
                "row_count": 572,
                "crowding_snapshot_count": 42,
                "order_book_snapshot_count": 7,
                "liquidation_snapshot_count": 3,
            },
            "aggregate_forward_paper": {
                "calendar_days": 0,
                "total_cumulative_signals": 0,
                "total_closed_trades": 0,
            },
        },
    )

    report = build_research_stream_health_report(root=tmp_path, include_systemd=False)

    assert report["schema_version"] == "research.droplet_stream_health.v1"
    assert report["overall_status"] == "ok"
    assert report["warnings"] == []
    streams = report["streams"]
    assert streams["ct145_forward_paper"]["latest_decision_time"] == "2026-05-27T11:00:00Z"
    assert streams["ct145_forward_paper"]["metrics"]["trade_count"] == 0
    assert streams["ct156_shadow_forward_paper"]["latest_decision_time"] == "2026-05-27T11:00:00Z"
    assert streams["ct180_oi_europe_shadow_forward_paper"]["row_counts"]["futures_metrics"] == 396
    assert streams["ct149_whale_watchlist"]["latest_snapshot"]["position_count"] == 0
    assert streams["ct151_binance_crowding"]["row_count"] == 55
    assert streams["ct151_binance_crowding"]["symbol_count"] == 2
    assert streams["ct158_binance_order_book"]["row_count"] == 451
    assert streams["ct158_binance_order_book"]["level_row_count"] == 440
    assert streams["ct160_binance_liquidations"]["row_count"] == 0
    assert streams["ct160_binance_liquidations"]["event_count_total"] == 0
    assert streams["ct162_external_forward_features"]["row_count"] == 44
    assert streams["ct162_external_forward_features"]["crowding_snapshot_count"] == 2
    assert streams["ct164_evidence_readiness"]["readiness_status"] == "not_ready"
    assert streams["ct164_evidence_readiness"]["external_feature_rows"] == 572


def test_build_research_stream_health_report_warns_on_missing_files_and_bad_crowding_count(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "data/generated/ct151_binance_crowding_forward/crowding_run.json",
        {
            "latest_generated_at": "2026-05-27T10:58:20Z",
            "generator_version": "ct153.binance_crowding_forward.v2",
            "row_count": 33,
            "period": "5m",
            "symbols": ["BTCUSDT"],
            "warnings": [],
        },
    )

    report = build_research_stream_health_report(root=tmp_path, include_systemd=False)

    assert report["overall_status"] == "warning"
    assert any("expected CT-153 healthy row_count=55" in warning for warning in report["warnings"])
    assert any("expected CT-158 healthy row_count=451" in warning for warning in report["warnings"])
    assert any("missing file" in warning for warning in report["warnings"])


def test_build_research_stream_health_report_includes_systemd_state(tmp_path: Path) -> None:
    def fake_systemd_reader(unit: str) -> dict[str, object]:
        return {
            "active_state": "active",
            "sub_state": "running" if unit.endswith(".service") else "waiting",
            "result": "success",
            "exec_main_status": "0",
        }

    report = build_research_stream_health_report(
        root=tmp_path,
        include_systemd=True,
        systemd_reader=fake_systemd_reader,
    )

    service = report["streams"]["ct145_forward_paper"]["service"]
    assert service["checked"] is True
    assert service["active_state"] == "active"


def test_build_research_stream_health_report_accepts_successful_inactive_oneshot_service(
    tmp_path: Path,
) -> None:
    def fake_systemd_reader(unit: str) -> dict[str, object]:
        if unit.endswith(".service"):
            return {
                "active_state": "inactive",
                "sub_state": "dead",
                "result": "success",
                "exec_main_status": "0",
            }
        return {
            "active_state": "active",
            "sub_state": "waiting",
            "result": "success",
            "exec_main_status": "0",
        }

    report = build_research_stream_health_report(
        root=tmp_path,
        include_systemd=True,
        systemd_reader=fake_systemd_reader,
    )

    assert not any("service is inactive" in warning for warning in report["warnings"])


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
