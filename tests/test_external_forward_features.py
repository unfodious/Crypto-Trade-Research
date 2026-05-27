import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from crypto_trade_research.data.external_forward_features import (
    ExternalForwardFeatureConfig,
    ExternalForwardFeatureError,
    build_external_forward_features,
)


def test_build_external_forward_features_writes_point_in_time_rows(tmp_path: Path) -> None:
    generated_at = datetime(2026, 5, 27, 10, 45, tzinfo=UTC)
    _write_crowding_snapshot(tmp_path, generated_at)
    _write_order_book_snapshot(tmp_path, generated_at)
    _write_liquidation_snapshot(tmp_path, generated_at)

    manifest = build_external_forward_features(
        ExternalForwardFeatureConfig(
            source_root=tmp_path,
            output_dir=tmp_path / "data/generated",
            dataset_prefix="unit_external_forward_features",
            generator_version="unit.external.v1",
            generated_at=datetime(2026, 5, 27, 11, tzinfo=UTC),
            symbols=("BTCUSDT", "ETHUSDT"),
            crowding_prefix="data/generated/ct151_binance_crowding_forward",
            order_book_prefix="data/generated/ct158_binance_order_book_forward",
            liquidation_prefix="data/generated/ct160_binance_liquidations_forward",
        )
    )

    assert manifest.row_count == 6
    assert manifest.crowding_snapshot_count == 1
    assert manifest.order_book_snapshot_count == 1
    assert manifest.liquidation_snapshot_count == 1
    assert manifest.symbols == ("BTCUSDT", "ETHUSDT")
    assert manifest.features_path.exists()
    assert manifest.manifest_path.exists()
    assert len(manifest.features_sha256) == 64

    rows = pq.read_table(manifest.features_path).to_pylist()
    btc_crowding = _find_row(rows, "BTCUSDT", "crowding")
    assert btc_crowding["source_available_at"] == generated_at
    assert btc_crowding["crowding_open_interest"] == pytest.approx(1000.0)
    assert btc_crowding["crowding_sum_open_interest_value"] == pytest.approx(250000.0)
    assert btc_crowding["global_long_short_ratio"] == pytest.approx(1.2)
    assert btc_crowding["top_trader_position_long_short_ratio"] == pytest.approx(1.3)
    assert btc_crowding["top_trader_account_long_short_ratio"] == pytest.approx(1.4)

    eth_order_book = _find_row(rows, "ETHUSDT", "order_book")
    assert eth_order_book["order_book_spread_bps"] == pytest.approx(3.5)
    assert eth_order_book["order_book_notional_imbalance"] == pytest.approx(-0.2)

    btc_liquidations = _find_row(rows, "BTCUSDT", "liquidations")
    assert btc_liquidations["source_available_at"] == datetime(2026, 5, 27, 10, 46, tzinfo=UTC)
    assert btc_liquidations["liquidation_event_count"] == 2
    assert btc_liquidations["liquidation_notional_total"] == pytest.approx(300.0)
    assert btc_liquidations["long_liquidation_notional"] == pytest.approx(100.0)
    assert btc_liquidations["short_liquidation_notional"] == pytest.approx(200.0)
    assert btc_liquidations["liquidation_notional_imbalance"] == pytest.approx(-1 / 3)

    eth_liquidations = _find_row(rows, "ETHUSDT", "liquidations")
    assert eth_liquidations["liquidation_event_count"] == 0
    assert eth_liquidations["liquidation_notional_total"] == pytest.approx(0.0)

    run_summary_path = (
        tmp_path
        / "data/generated/unit_external_forward_features/external_forward_features_run.json"
    )
    run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    assert run_summary["row_count"] == 6
    assert run_summary["crowding_snapshot_count"] == 1
    assert run_summary["order_book_snapshot_count"] == 1
    assert run_summary["liquidation_snapshot_count"] == 1


def test_build_external_forward_features_rejects_empty_sources(tmp_path: Path) -> None:
    with pytest.raises(ExternalForwardFeatureError, match="no external forward feature rows"):
        build_external_forward_features(
            ExternalForwardFeatureConfig(
                source_root=tmp_path,
                output_dir=tmp_path / "data/generated",
                dataset_prefix="unit_external_forward_features",
                generator_version="unit.external.v1",
                symbols=("BTCUSDT",),
                crowding_prefix="data/generated/ct151_binance_crowding_forward",
                order_book_prefix="data/generated/ct158_binance_order_book_forward",
                liquidation_prefix="data/generated/ct160_binance_liquidations_forward",
            )
        )


def _find_row(rows: list[dict[str, object]], symbol: str, family: str) -> dict[str, object]:
    return next(row for row in rows if row["symbol"] == symbol and row["feature_family"] == family)


def _write_crowding_snapshot(root: Path, generated_at: datetime) -> None:
    dataset_dir = root / "data/generated/ct151_binance_crowding_forward_20260527T104500Z"
    clean_dir = dataset_dir / "clean"
    _write_table(
        clean_dir / "current_open_interest.parquet",
        [
            {"symbol": "BTCUSDT", "source_available_at": generated_at, "open_interest": 1000.0},
            {"symbol": "ETHUSDT", "source_available_at": generated_at, "open_interest": 2000.0},
        ],
    )
    _write_table(
        clean_dir / "open_interest_hist.parquet",
        [
            {
                "symbol": "BTCUSDT",
                "source_available_at": generated_at,
                "sum_open_interest": 1000.0,
                "sum_open_interest_value": 250000.0,
            },
            {
                "symbol": "ETHUSDT",
                "source_available_at": generated_at,
                "sum_open_interest": 2000.0,
                "sum_open_interest_value": 500000.0,
            },
        ],
    )
    _write_table(
        clean_dir / "global_long_short_ratio.parquet",
        [
            {"symbol": "BTCUSDT", "source_available_at": generated_at, "long_short_ratio": 1.2},
            {"symbol": "ETHUSDT", "source_available_at": generated_at, "long_short_ratio": 0.8},
        ],
    )
    _write_table(
        clean_dir / "top_long_short_position_ratio.parquet",
        [
            {"symbol": "BTCUSDT", "source_available_at": generated_at, "long_short_ratio": 1.3},
            {"symbol": "ETHUSDT", "source_available_at": generated_at, "long_short_ratio": 0.7},
        ],
    )
    _write_table(
        clean_dir / "top_long_short_account_ratio.parquet",
        [
            {"symbol": "BTCUSDT", "source_available_at": generated_at, "long_short_ratio": 1.4},
            {"symbol": "ETHUSDT", "source_available_at": generated_at, "long_short_ratio": 0.6},
        ],
    )
    _write_json(
        dataset_dir / "manifest.json",
        {
            "dataset_name": dataset_dir.name,
            "generated_at": "2026-05-27T10:45:00Z",
            "current_open_interest_path": str(
                Path("data/generated") / dataset_dir.name / "clean/current_open_interest.parquet"
            ),
            "open_interest_hist_path": str(
                Path("data/generated") / dataset_dir.name / "clean/open_interest_hist.parquet"
            ),
            "global_long_short_path": str(
                Path("data/generated") / dataset_dir.name / "clean/global_long_short_ratio.parquet"
            ),
            "top_long_short_position_path": str(
                Path("data/generated")
                / dataset_dir.name
                / "clean/top_long_short_position_ratio.parquet"
            ),
            "top_long_short_account_path": str(
                Path("data/generated")
                / dataset_dir.name
                / "clean/top_long_short_account_ratio.parquet"
            ),
        },
    )


def _write_order_book_snapshot(root: Path, generated_at: datetime) -> None:
    dataset_dir = root / "data/generated/ct158_binance_order_book_forward_20260527T104500Z"
    clean_dir = dataset_dir / "clean"
    _write_table(
        clean_dir / "order_book_summary.parquet",
        [
            {
                "symbol": "BTCUSDT",
                "source_available_at": generated_at,
                "spread_bps": 2.0,
                "bid_notional_total": 10000.0,
                "ask_notional_total": 8000.0,
                "notional_imbalance": 0.111,
                "largest_bid_notional": 3000.0,
                "largest_bid_distance_bps": 5.0,
                "largest_ask_notional": 2500.0,
                "largest_ask_distance_bps": 7.0,
            },
            {
                "symbol": "ETHUSDT",
                "source_available_at": generated_at,
                "spread_bps": 3.5,
                "bid_notional_total": 4000.0,
                "ask_notional_total": 6000.0,
                "notional_imbalance": -0.2,
                "largest_bid_notional": 1500.0,
                "largest_bid_distance_bps": 4.0,
                "largest_ask_notional": 2200.0,
                "largest_ask_distance_bps": 6.0,
            },
        ],
    )
    _write_json(
        dataset_dir / "manifest.json",
        {
            "dataset_name": dataset_dir.name,
            "generated_at": "2026-05-27T10:45:00Z",
            "summary_path": str(
                Path("data/generated") / dataset_dir.name / "clean/order_book_summary.parquet"
            ),
        },
    )


def _write_liquidation_snapshot(root: Path, generated_at: datetime) -> None:
    dataset_dir = root / "data/generated/ct160_binance_liquidations_forward_20260527T104500Z"
    clean_dir = dataset_dir / "clean"
    _write_table(
        clean_dir / "liquidations.parquet",
        [
            {
                "symbol": "BTCUSDT",
                "source_available_at": generated_at,
                "notional": 100.0,
                "liquidation_direction": "long_liquidation",
            },
            {
                "symbol": "BTCUSDT",
                "source_available_at": generated_at,
                "notional": 200.0,
                "liquidation_direction": "short_liquidation",
            },
            {
                "symbol": "DOGEUSDT",
                "source_available_at": generated_at,
                "notional": 999.0,
                "liquidation_direction": "long_liquidation",
            },
        ],
    )
    _write_json(
        dataset_dir / "manifest.json",
        {
            "dataset_name": dataset_dir.name,
            "generated_at": "2026-05-27T10:45:00Z",
            "capture_ended_at": "2026-05-27T10:46:00Z",
            "liquidations_path": str(
                Path("data/generated") / dataset_dir.name / "clean/liquidations.parquet"
            ),
        },
    )


def _write_table(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
