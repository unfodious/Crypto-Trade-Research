from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_trade_research.futures_metrics_selected_features import (
    FuturesMetricsSelectedFeaturesConfig,
    FuturesMetricsSelectedWindowConfig,
    build_futures_metrics_selected_features,
)


def test_build_futures_metrics_selected_features_uses_last_point_in_time_metric(
    tmp_path: Path,
) -> None:
    metrics_path = tmp_path / "metrics.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                _metric_row(
                    "BTCUSDT",
                    datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                    oi_value=100,
                    global_ratio=1.0,
                    top_ratio=1.1,
                    taker_ratio=1.2,
                ),
                _metric_row(
                    "ETHUSDT",
                    datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                    oi_value=200,
                    global_ratio=1.4,
                    top_ratio=1.5,
                    taker_ratio=1.6,
                ),
                _metric_row(
                    "BTCUSDT",
                    datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
                    oi_value=125,
                    global_ratio=1.3,
                    top_ratio=1.8,
                    taker_ratio=1.6,
                ),
                _metric_row(
                    "ETHUSDT",
                    datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
                    oi_value=250,
                    global_ratio=1.1,
                    top_ratio=1.2,
                    taker_ratio=0.9,
                ),
            ]
        ),
        metrics_path,
    )
    replay_dir = tmp_path / "replay"
    selected_path = replay_dir / "candidate" / "selected_trades.parquet"
    selected_path.parent.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "h12",
                    "decision_time": datetime(2026, 1, 1, 1, 5, tzinfo=UTC),
                },
                {
                    "symbol": "ETHUSDT",
                    "timeframe": "h12",
                    "decision_time": datetime(2026, 1, 1, 1, 20, tzinfo=UTC),
                },
            ]
        ),
        selected_path,
    )
    replay_report_path = replay_dir / "replay_report.json"
    replay_report_path.write_text(
        json.dumps({"replays": [{"trades_path": "candidate/selected_trades.parquet"}]}),
        encoding="utf-8",
    )
    output_path = tmp_path / "features.parquet"

    payload = build_futures_metrics_selected_features(
        FuturesMetricsSelectedFeaturesConfig(
            metrics_path=metrics_path,
            max_metrics_age_minutes=10,
            windows=(
                FuturesMetricsSelectedWindowConfig(
                    name="unit",
                    replay_report_path=replay_report_path,
                    output_path=output_path,
                ),
            ),
        )
    )

    assert payload["windows"][0]["row_count"] == 2
    assert payload["windows"][0]["matched_metrics_count"] == 1
    rows = pq.read_table(output_path).to_pylist()
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["fm_metrics_match"] == 1
    assert rows[0]["fm_metrics_age_minutes"] == 5
    assert rows[0]["fm_oi_value_change_1h"] == 0.25
    assert rows[0]["fm_top_vs_global_ratio_spread"] == 0.5
    assert rows[0]["fm_global_vs_market_median_spread"] == pytest.approx(0.1)
    assert rows[0]["fm_session_asia"] == 1
    assert rows[0]["fm_session_europe"] == 0
    assert rows[0]["fm_symbol_btc"] == 1
    assert rows[0]["fm_symbol_group_ada_icp_sui"] == 0
    assert rows[1]["symbol"] == "ETHUSDT"
    assert rows[1]["fm_metrics_match"] == 0
    assert rows[1]["fm_sum_open_interest_value"] is None
    assert rows[1]["fm_session_asia"] == 1
    assert rows[1]["fm_symbol_eth"] == 1


def _metric_row(
    symbol: str,
    metrics_time: datetime,
    *,
    oi_value: float,
    global_ratio: float | None,
    top_ratio: float | None,
    taker_ratio: float | None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "metrics_time": metrics_time,
        "sum_open_interest_value": oi_value,
        "count_toptrader_long_short_ratio": top_ratio,
        "sum_toptrader_long_short_ratio": top_ratio,
        "count_long_short_ratio": global_ratio,
        "sum_taker_long_short_vol_ratio": taker_ratio,
    }
