import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_trade_research.spot_aggtrade_flow import (
    SpotAggTradeFlowConfig,
    build_spot_aggtrade_flow_report,
)


def test_spot_aggtrade_flow_report_scores_pre_entry_aggressive_buy_pressure(
    tmp_path: Path,
) -> None:
    entry_time = datetime(2025, 3, 1, 12, 30, tzinfo=UTC)
    config = SpotAggTradeFlowConfig.from_dict(
        {
            "report_name": "unit_aggtrade_flow",
            "issue_id": "CT-198",
            "epic_id": "CT-113",
            "source_spot_config_path": "/tmp/unused.json",
            "output_json_path": str(tmp_path / "report.json"),
            "output_markdown_path": str(tmp_path / "report.md"),
            "cache_dir": str(tmp_path / "cache"),
            "scenario_names": ["unit"],
            "lookback_minutes": 30,
        }
    )
    candidate_rows = [
        {
            "scenario": "unit",
            "window": "unit",
            "symbol": "SOLUSDT",
            "entry_time": entry_time.isoformat().replace("+00:00", "Z"),
            "status": "closed",
            "exit_reason": "profit_fade",
            "net_return_pct": 0.05,
        }
    ]

    payload = build_spot_aggtrade_flow_report(
        config,
        candidate_rows=candidate_rows,
        fetch_zip=lambda _url: _aggtrade_zip(entry_time),
    )

    scenario = payload["scenarios"][0]
    assert scenario["candidate_count"] == 1
    assert scenario["average_net_return_pct"] == pytest.approx(0.05)
    assert scenario["average_buy_ratio"] == pytest.approx(110 / 160)
    assert scenario["average_imbalance"] == pytest.approx((110 - 50) / 160)
    assert (tmp_path / "report.md").exists()


def test_spot_aggtrade_flow_report_accepts_headerless_data_vision_rows(tmp_path: Path) -> None:
    entry_time = datetime(2025, 3, 1, 12, 30, tzinfo=UTC)
    config = SpotAggTradeFlowConfig.from_dict(
        {
            "report_name": "unit_aggtrade_flow",
            "issue_id": "CT-198",
            "epic_id": "CT-113",
            "source_spot_config_path": "/tmp/unused.json",
            "output_json_path": str(tmp_path / "report.json"),
            "output_markdown_path": str(tmp_path / "report.md"),
            "cache_dir": str(tmp_path / "cache"),
            "scenario_names": ["unit"],
            "lookback_minutes": 30,
        }
    )

    payload = build_spot_aggtrade_flow_report(
        config,
        candidate_rows=[
            {
                "scenario": "unit",
                "window": "unit",
                "symbol": "SOLUSDT",
                "entry_time": entry_time.isoformat().replace("+00:00", "Z"),
                "net_return_pct": 0.01,
            }
        ],
        fetch_zip=lambda _url: _aggtrade_zip(entry_time, include_header=False),
    )

    assert payload["scenarios"][0]["candidate_count"] == 1
    assert payload["scenarios"][0]["average_buy_ratio"] == pytest.approx(110 / 160)


def _aggtrade_zip(entry_time: datetime, *, include_header: bool = True) -> bytes:
    output = io.BytesIO()
    header = [
        [
            "agg_trade_id",
            "price",
            "quantity",
            "first_trade_id",
            "last_trade_id",
            "transact_time",
            "is_buyer_maker",
            "is_best_match",
        ],
    ]
    rows = [
        _row(entry_time - timedelta(minutes=20), price=10, quantity=5, is_buyer_maker=True),
        _row(entry_time - timedelta(minutes=10), price=10, quantity=8, is_buyer_maker=False),
        _row(entry_time - timedelta(minutes=1), price=10, quantity=3, is_buyer_maker=False),
        _row(entry_time + timedelta(minutes=1), price=10, quantity=100, is_buyer_maker=False),
    ]
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "SOLUSDT-aggTrades-2025-03-01.csv",
            "\n".join(
                ",".join(str(value) for value in row)
                for row in ([*header, *rows] if include_header else rows)
            ),
        )
    return output.getvalue()


def _row(
    trade_time: datetime,
    *,
    price: float,
    quantity: float,
    is_buyer_maker: bool,
) -> list[object]:
    return [
        1,
        price,
        quantity,
        1,
        1,
        int(trade_time.timestamp() * 1000),
        str(is_buyer_maker).lower(),
        "true",
    ]
