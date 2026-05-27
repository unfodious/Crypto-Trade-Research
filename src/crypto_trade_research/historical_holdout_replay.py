"""Replay frozen paper-pack candidates on an older historical holdout."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.backtest import BacktestConfig, SignalRow, evaluate_signal_strategy
from crypto_trade_research.features import FeatureConfig, generate_ohlcv_features
from crypto_trade_research.labels import LabelConfig, generate_trade_labels_for_keys
from crypto_trade_research.models.artifacts import ModelArtifact, load_model_artifact

SCHEMA_VERSION = "research.historical-holdout-replay.v1"


@dataclass(frozen=True, slots=True)
class HistoricalHoldoutReplayConfig:
    run_name: str
    output_dir: Path
    issue_id: str
    epic_id: str
    dataset_manifest_path: Path
    funding_manifest_path: Path
    pack_manifest_paths: tuple[Path, ...]
    feature_set_version: str
    rolling_window: int
    higher_timeframes: tuple[str, ...]
    generated_at: datetime

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HistoricalHoldoutReplayConfig:
        feature = dict(payload["feature"])
        return cls(
            run_name=str(payload["run_name"]),
            output_dir=Path(str(payload["output_dir"])),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            dataset_manifest_path=Path(str(payload["dataset_manifest_path"])),
            funding_manifest_path=Path(str(payload["funding_manifest_path"])),
            pack_manifest_paths=tuple(Path(str(path)) for path in payload["pack_manifest_paths"]),
            feature_set_version=str(feature["feature_set_version"]),
            rolling_window=int(feature.get("rolling_window", 20)),
            higher_timeframes=tuple(str(item) for item in feature.get("higher_timeframes", ())),
            generated_at=_parse_timestamp(str(payload["generated_at"])),
        )

    @classmethod
    def from_path(cls, path: Path) -> HistoricalHoldoutReplayConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def run_historical_holdout_replay(config: HistoricalHoldoutReplayConfig) -> dict[str, object]:
    """Apply frozen pack rules and model artifacts to an older holdout."""

    source_rows = _read_manifest_rows(config.dataset_manifest_path)
    funding_rows = _read_manifest_rows(config.funding_manifest_path)
    features = generate_ohlcv_features(
        source_rows,
        FeatureConfig(
            feature_set_version=config.feature_set_version,
            rolling_window=config.rolling_window,
            higher_timeframes=config.higher_timeframes,
        ),
        funding_rate_rows=funding_rows,
    )
    entry_prices = _entry_prices(source_rows)
    replays = [
        _replay_pack(pack_path, source_rows, features.rows, entry_prices)
        for pack_path in config.pack_manifest_paths
    ]
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_name": config.run_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "generated_at": _format_timestamp(config.generated_at),
        "dataset_manifest_path": str(config.dataset_manifest_path),
        "funding_manifest_path": str(config.funding_manifest_path),
        "row_counts": {
            "source_rows": len(source_rows),
            "funding_rows": len(funding_rows),
            "feature_rows": len(features.rows),
        },
        "replays": replays,
        "decision": {
            "live_trading_approved": False,
            "working_model": False,
            "evidence_type": "older_historical_holdout",
        },
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(config.output_dir / "replay_report.json", payload)
    _write_markdown(config.output_dir / "replay_report.md", payload)
    return payload


def _replay_pack(
    pack_path: Path,
    source_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    entry_prices: dict[tuple[object, ...], float],
) -> dict[str, object]:
    pack = _read_json(pack_path)
    artifact = _load_pack_model_artifact(pack)
    if artifact.expected_r_model is None:
        raise ValueError("historical holdout replay requires expected_r_model")
    strategy = dict(pack["strategy"])
    candidate_rows = _candidate_rows(feature_rows, strategy)
    scored_rows = _score_and_rank(candidate_rows, artifact, strategy, entry_prices)
    selected_rows = [row for row in scored_rows if row["paper_take"]]
    label_config = _label_config(strategy)
    labels = generate_trade_labels_for_keys(source_rows, label_config, _label_keys(selected_rows))
    labels_by_key = {_label_key(row): row for row in labels.rows}
    signals = _signals(selected_rows, labels_by_key, strategy)
    report = evaluate_signal_strategy(
        str(pack["candidate_name"]),
        signals,
        _backtest_config(strategy),
    )
    selected_with_labels = [
        _trade_row(row, labels_by_key.get(_feature_label_key(row))) for row in selected_rows
    ]
    accepted_trades = _report_trade_rows(report.trades)
    output_dir = Path(str(pack["pack_name"]))
    return {
        "pack_manifest_path": str(pack_path),
        "pack_name": str(pack["pack_name"]),
        "candidate_name": str(pack["candidate_name"]),
        "model_id": artifact.model_id,
        "symbols": list(strategy.get("symbols", ())),
        "filters": strategy.get("filters", ()),
        "ranking": strategy.get("ranking", {}),
        "candidate_count": len(candidate_rows),
        "scored_count": len(scored_rows),
        "selected_count": len(selected_rows),
        "label_count": len(labels.rows),
        "metrics": asdict(report.metrics),
        "symbol_metrics": _symbol_metrics(accepted_trades),
        "session_metrics": _session_metrics(accepted_trades),
        "accepted_trades": accepted_trades,
        "accepted_trades_path": str(output_dir / "accepted_trades.parquet"),
        "trades_path": str(output_dir / "selected_trades.parquet"),
        "trades": selected_with_labels,
    }


def _load_pack_model_artifact(pack: dict[str, object]) -> ModelArtifact:
    source_artifacts = dict(pack["source_artifacts"])
    model_ref = dict(source_artifacts["model_artifact"])
    return load_model_artifact(Path(str(model_ref["path"])))


def _candidate_rows(
    rows: list[dict[str, object]],
    strategy: dict[str, object],
) -> list[dict[str, object]]:
    filters = [dict(item) for item in strategy.get("filters", ())]
    symbols = {str(symbol) for symbol in strategy.get("symbols", ())}
    return [
        row
        for row in rows
        if str(row.get("symbol")) in symbols and all(_filter_passes(row, item) for item in filters)
    ]


def _filter_passes(row: dict[str, object], item: dict[str, object]) -> bool:
    raw_value = row.get(str(item["feature"]))
    if raw_value is None:
        return False
    value = float(raw_value)
    threshold = float(item["value"])
    operator = str(item["operator"])
    if operator == "<=":
        return value <= threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == ">":
        return value > threshold
    raise ValueError(f"unsupported filter operator: {operator}")


def _score_and_rank(
    rows: list[dict[str, object]],
    artifact: ModelArtifact,
    strategy: dict[str, object],
    entry_prices: dict[tuple[object, ...], float],
) -> list[dict[str, object]]:
    ranking = dict(strategy.get("ranking", {}))
    threshold = float(ranking.get("selected_expected_r_threshold", 0.0))
    top_n = int(ranking.get("top_n_per_decision_time", 1))
    by_time: dict[datetime, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        prediction = artifact.predict(_feature_values(row, artifact))
        if prediction.expected_r is None:
            continue
        scored = dict(row)
        scored["entry_price"] = entry_prices[_row_key(row, "decision_time")]
        scored["expected_r"] = float(prediction.expected_r)
        scored["target_before_stop_probability"] = float(prediction.target_before_stop_probability)
        scored["expected_r_threshold_passed"] = prediction.expected_r >= threshold
        by_time[_as_datetime(row["decision_time"])].append(scored)

    ranked: list[dict[str, object]] = []
    for decision_time in sorted(by_time):
        ordered = sorted(
            by_time[decision_time],
            key=lambda item: (float(item["expected_r"]), str(item["symbol"])),
            reverse=True,
        )
        for rank, row in enumerate(ordered, start=1):
            row["rank"] = rank
            row["top_n_passed"] = rank <= top_n
            row["paper_take"] = bool(row["expected_r_threshold_passed"]) and rank <= top_n
            ranked.append(row)
    return ranked


def _feature_values(row: dict[str, object], artifact: ModelArtifact) -> dict[str, float]:
    return {
        name: float(row[name])
        for name in artifact.feature_schema.feature_names
        if name in row and row[name] is not None
    }


def _signals(
    selected_rows: list[dict[str, object]],
    labels_by_key: dict[tuple[object, ...], dict[str, object]],
    strategy: dict[str, object],
) -> list[SignalRow]:
    signals = []
    for row in selected_rows:
        label = labels_by_key.get(_feature_label_key(row))
        if label is None or label["realized_r_after_costs"] is None:
            continue
        signals.append(
            SignalRow(
                decision_time=_as_datetime(row["decision_time"]),
                symbol=str(row["symbol"]),
                timeframe=str(row["timeframe"]),
                side=str(strategy.get("side", "long")),
                gross_r=float(label["realized_r_after_costs"]),
                confidence=_expected_r_confidence(float(row["expected_r"])),
                exit_time=_as_datetime(label["source_window_end"])
                if label.get("source_window_end") is not None
                else None,
            )
        )
    return signals


def _trade_row(
    row: dict[str, object],
    label: dict[str, object] | None,
) -> dict[str, object]:
    output = {
        "decision_time": _format_timestamp(_as_datetime(row["decision_time"])),
        "symbol": str(row["symbol"]),
        "timeframe": str(row["timeframe"]),
        "entry_price": float(row["entry_price"]),
        "expected_r": float(row["expected_r"]),
        "target_before_stop_probability": float(row["target_before_stop_probability"]),
        "rank": int(row["rank"]),
    }
    if label is not None:
        output.update(
            {
                "realized_r_after_costs": _optional_float(label["realized_r_after_costs"]),
                "target_before_stop": label["target_before_stop"],
                "max_favorable_excursion_r": _optional_float(label["max_favorable_excursion_r"]),
                "max_adverse_excursion_r": _optional_float(label["max_adverse_excursion_r"]),
                "exit_time": _format_timestamp(_as_datetime(label["source_window_end"]))
                if label.get("source_window_end") is not None
                else None,
            }
        )
    return output


def _symbol_metrics(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return _group_metrics(rows, "symbol")


def _session_metrics(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    session_rows = [dict(row, session=_session(row["decision_time"])) for row in rows]
    return _group_metrics(session_rows, "session")


def _group_metrics(rows: list[dict[str, object]], field: str) -> list[dict[str, object]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get("net_r")
        if value is not None:
            groups[str(row[field])].append(float(value))
    return [
        {
            field: key,
            "trade_count": len(values),
            "average_r": sum(values) / len(values) if values else 0.0,
            "positive": bool(values and sum(values) / len(values) > 0),
        }
        for key, values in sorted(groups.items())
    ]


def _report_trade_rows(trades: list[object]) -> list[dict[str, object]]:
    return [
        {
            "decision_time": _format_timestamp(trade.decision_time),
            "exit_time": _format_timestamp(trade.exit_time),
            "symbol": trade.symbol,
            "timeframe": trade.timeframe,
            "side": trade.side,
            "net_r": trade.net_r,
            "pnl": trade.pnl,
            "risk_pct": trade.risk_pct,
        }
        for trade in trades
    ]


def _label_config(strategy: dict[str, object]) -> LabelConfig:
    exits = dict(strategy["exits"])
    cost_model = dict(strategy.get("cost_model", {}))
    return LabelConfig(
        label_set_version="labels.ct169.older-holdout-replay.v1",
        horizon_bars=int(exits["horizon_bars"]),
        side=str(strategy.get("side", "long")),
        stop_loss_pct=float(exits["stop_loss_pct"]),
        target_pct=float(exits["target_pct"]),
        cost_pct=float(cost_model.get("round_trip_cost_pct", 0.0)),
        flat_threshold_pct=0.0002,
        target_stop_tie_breaker=str(exits.get("target_stop_tie_breaker", "stop_first")),
    )


def _backtest_config(strategy: dict[str, object]) -> BacktestConfig:
    risk_controls = dict(strategy.get("risk_controls", {}))
    return BacktestConfig(
        initial_equity=10000,
        risk_per_trade_pct=0.01,
        max_trades_per_symbol=_optional_int(risk_controls.get("max_trades_per_symbol")),
        max_trades_per_decision_time=_optional_int(
            risk_controls.get("max_trades_per_decision_time")
        ),
        loss_cooldown_signals=int(risk_controls.get("loss_cooldown_signals", 0)),
    )


def _label_keys(rows: list[dict[str, object]]) -> set[tuple[object, ...]]:
    return {_feature_label_key(row) for row in rows}


def _feature_label_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        _as_datetime(row["decision_time"]),
    )


def _label_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        _as_datetime(row["decision_time"]),
    )


def _entry_prices(rows: list[dict[str, object]]) -> dict[tuple[object, ...], float]:
    return {_row_key(row, "close_time"): float(row["close"]) for row in rows}


def _row_key(row: dict[str, object], time_field: str) -> tuple[object, ...]:
    return (
        row["venue"],
        row["market_type"],
        row["symbol"],
        row["timeframe"],
        _as_datetime(row[time_field]),
    )


def _read_manifest_rows(manifest_path: Path) -> list[dict[str, object]]:
    payload = _read_json(manifest_path)
    return [dict(row) for row in pq.read_table(Path(str(payload["cleaned_path"]))).to_pylist()]


def _write_markdown(path: Path, payload: dict[str, object]) -> None:
    lines = [
        f"# {payload['run_name']}",
        "",
        f"- dataset: `{payload['dataset_manifest_path']}`",
        f"- funding: `{payload['funding_manifest_path']}`",
        f"- source rows: `{dict(payload['row_counts'])['source_rows']}`",
        "",
        "| candidate | trades | avg R | max DD | profit factor |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for replay in payload["replays"]:
        metrics = dict(replay["metrics"])
        lines.append(
            "| "
            f"{replay['candidate_name']} | "
            f"{metrics['trade_count']} | "
            f"{metrics['average_r']:.4f} | "
            f"{metrics['max_drawdown_pct']:.2%} | "
            f"{metrics['profit_factor']:.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_trade_parquets(output_dir: Path, payload: dict[str, object]) -> None:
    for replay in payload["replays"]:
        trades_path = output_dir / str(replay["trades_path"])
        trades_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(list(replay["trades"])), trades_path)
        accepted_trades_path = output_dir / str(replay["accepted_trades_path"])
        accepted_trades_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(
            pa.Table.from_pylist(list(replay["accepted_trades"])),
            accepted_trades_path,
        )


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_trade_parquets(path.parent, payload)
    slim_payload = {
        **payload,
        "replays": [
            {
                key: value
                for key, value in dict(replay).items()
                if key not in {"trades", "accepted_trades"}
            }
            for replay in payload["replays"]
        ],
    }
    path.write_text(json.dumps(slim_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _session(value: object) -> str:
    hour = _parse_timestamp(str(value)).hour
    if 0 <= hour < 8:
        return "asia"
    if 8 <= hour < 16:
        return "europe"
    return "us"


def _expected_r_confidence(expected_r: float) -> float:
    return min(1.0, max(0.01, expected_r))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return _parse_timestamp(str(value))


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = run_historical_holdout_replay(HistoricalHoldoutReplayConfig.from_path(args.config))
    for replay in payload["replays"]:
        metrics = dict(replay["metrics"])
        print(
            f"{replay['candidate_name']}: trades={metrics['trade_count']} "
            f"avg_r={metrics['average_r']:.4f} "
            f"max_dd={metrics['max_drawdown_pct']:.2%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
