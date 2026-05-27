"""Run fast abstention sensitivity checks on cached selected trades."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.backtest import BacktestConfig, SignalRow, evaluate_signal_strategy

SCHEMA_VERSION = "research.selected-trade-abstention.v1"
KEY_COLUMNS = ("symbol", "timeframe", "decision_time")


class SelectedTradeAbstentionError(ValueError):
    """Raised when selected-trade abstention analysis cannot be built."""


@dataclass(frozen=True, slots=True)
class AbstentionRule:
    name: str
    filters: tuple[dict[str, object], ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AbstentionRule:
        return cls(
            name=str(payload["name"]),
            filters=tuple(dict(item) for item in payload.get("filters", ())),
        )


@dataclass(frozen=True, slots=True)
class AbstentionWindowConfig:
    name: str
    replay_report_path: Path
    feature_rows_path: Path

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AbstentionWindowConfig:
        return cls(
            name=str(payload["name"]),
            replay_report_path=Path(str(payload["replay_report_path"])),
            feature_rows_path=Path(str(payload["feature_rows_path"])),
        )


@dataclass(frozen=True, slots=True)
class SelectedTradeAbstentionConfig:
    report_name: str
    issue_id: str
    epic_id: str
    output_json_path: Path
    output_markdown_path: Path
    windows: tuple[AbstentionWindowConfig, ...]
    rules: tuple[AbstentionRule, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SelectedTradeAbstentionConfig:
        return cls(
            report_name=str(payload["report_name"]),
            issue_id=str(payload["issue_id"]),
            epic_id=str(payload["epic_id"]),
            output_json_path=Path(str(payload["output_json_path"])),
            output_markdown_path=Path(str(payload["output_markdown_path"])),
            windows=tuple(
                AbstentionWindowConfig.from_dict(dict(item)) for item in payload["windows"]
            ),
            rules=tuple(AbstentionRule.from_dict(dict(item)) for item in payload["rules"]),
        )

    @classmethod
    def from_path(cls, path: Path) -> SelectedTradeAbstentionConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def build_selected_trade_abstention_report(
    config: SelectedTradeAbstentionConfig,
) -> dict[str, object]:
    """Build a fast abstention sensitivity report from cached selected trades."""

    _validate_config(config)
    window_reports = [_window_report(window, config.rules) for window in config.windows]
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "report_name": config.report_name,
        "issue_id": config.issue_id,
        "epic_id": config.epic_id,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "windows": window_reports,
        "decision": {
            "working_model": False,
            "live_trading_approved": False,
            "notes": (
                "Research-only selected-trade sensitivity screen; "
                "full replay required before promotion."
            ),
        },
    }
    _write_report(config, payload)
    return payload


def _window_report(
    window: AbstentionWindowConfig,
    rules: tuple[AbstentionRule, ...],
) -> dict[str, object]:
    replay_report = _read_json(window.replay_report_path)
    feature_columns = _feature_columns(rules)
    candidate_reports: list[dict[str, object]] = []

    for replay in replay_report["replays"]:
        replay_item = dict(replay)
        selected_path = window.replay_report_path.parent / str(replay_item["trades_path"])
        selected_rows = _read_selected_rows(selected_path)
        joined_rows = _join_feature_columns(
            window.feature_rows_path,
            selected_rows,
            feature_columns,
        )
        pack = _read_json(Path(str(replay_item["pack_manifest_path"])))
        strategy = dict(pack["strategy"])
        rule_reports = [
            _rule_report(
                rule,
                joined_rows,
                candidate_name=str(replay_item["candidate_name"]),
                strategy=strategy,
            )
            for rule in _rules_with_baseline(rules)
        ]
        candidate_reports.append(
            {
                "candidate_name": str(replay_item["candidate_name"]),
                "pack_manifest_path": str(replay_item["pack_manifest_path"]),
                "selected_trades_path": str(selected_path),
                "source_base_metrics": replay_item.get("metrics", {}),
                "selected_row_count": len(selected_rows),
                "matched_feature_count": sum(1 for row in joined_rows if row["_feature_match"]),
                "rules": rule_reports,
            }
        )

    return {
        "name": window.name,
        "replay_report_path": str(window.replay_report_path),
        "feature_rows_path": str(window.feature_rows_path),
        "candidates": candidate_reports,
    }


def _rule_report(
    rule: AbstentionRule,
    rows: list[dict[str, object]],
    *,
    candidate_name: str,
    strategy: dict[str, object],
) -> dict[str, object]:
    kept_rows = rows if not rule.filters else [row for row in rows if not _rule_matches(row, rule)]
    signals = _signals(kept_rows, strategy)
    report = evaluate_signal_strategy(
        f"{candidate_name}:{rule.name}",
        signals,
        _backtest_config(strategy),
    )
    return {
        "name": rule.name,
        "filters": list(rule.filters),
        "selected_row_count": len(rows),
        "kept_row_count": len(kept_rows),
        "skipped_row_count": len(rows) - len(kept_rows),
        "metrics": asdict(report.metrics),
    }


def _rules_with_baseline(rules: tuple[AbstentionRule, ...]) -> tuple[AbstentionRule, ...]:
    return (AbstentionRule(name="base_recomputed", filters=()), *rules)


def _read_selected_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise SelectedTradeAbstentionError(f"missing selected trades parquet: {path}")
    return [dict(row) for row in pq.read_table(path).to_pylist()]


def _join_feature_columns(
    path: Path,
    selected_rows: list[dict[str, object]],
    feature_columns: tuple[str, ...],
) -> list[dict[str, object]]:
    if not path.exists():
        raise SelectedTradeAbstentionError(f"missing feature rows parquet: {path}")
    if not selected_rows:
        return []

    selected_table = pa.Table.from_pylist(
        [
            {
                **row,
                "_selected_index": index,
                "decision_time_iso": str(row["decision_time"]),
                "decision_time": _parse_timestamp(str(row["decision_time"])),
            }
            for index, row in enumerate(selected_rows)
        ]
    )
    feature_table = pq.read_table(
        path,
        columns=list(dict.fromkeys((*KEY_COLUMNS, *feature_columns))),
    )
    feature_table = feature_table.append_column(
        "_feature_match",
        pa.array([True] * feature_table.num_rows),
    )
    joined = selected_table.join(
        feature_table,
        keys=list(KEY_COLUMNS),
        join_type="left outer",
    )
    rows = sorted(joined.to_pylist(), key=lambda row: int(row["_selected_index"]))
    for row in rows:
        row["decision_time"] = str(row.pop("decision_time_iso"))
        row["_feature_match"] = bool(row.get("_feature_match"))
        row.pop("_selected_index", None)
    return rows


def _signals(rows: list[dict[str, object]], strategy: dict[str, object]) -> list[SignalRow]:
    side = str(strategy.get("side", "long"))
    signals: list[SignalRow] = []
    for row in rows:
        realized_r = row.get("realized_r_after_costs")
        if realized_r is None:
            continue
        signals.append(
            SignalRow(
                decision_time=_parse_timestamp(str(row["decision_time"])),
                symbol=str(row["symbol"]),
                timeframe=str(row["timeframe"]),
                side=side,
                gross_r=float(realized_r),
                confidence=_expected_r_confidence(float(row["expected_r"])),
                exit_time=_parse_timestamp(str(row["exit_time"])) if row.get("exit_time") else None,
            )
        )
    return signals


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


def _feature_columns(rules: tuple[AbstentionRule, ...]) -> tuple[str, ...]:
    columns = sorted({str(item["feature"]) for rule in rules for item in rule.filters})
    return tuple(columns)


def _rule_matches(row: dict[str, object], rule: AbstentionRule) -> bool:
    return all(_filter_passes(row, item) for item in rule.filters)


def _filter_passes(row: dict[str, object], item: dict[str, object]) -> bool:
    value = _number(row.get(str(item["feature"])))
    if value is None:
        return False
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
    raise SelectedTradeAbstentionError(f"unsupported filter operator: {operator}")


def _write_report(config: SelectedTradeAbstentionConfig, payload: dict[str, object]) -> None:
    config.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    config.output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown_path.write_text(_markdown_report(payload), encoding="utf-8")


def _markdown_report(payload: dict[str, object]) -> str:
    lines = [
        f"# {payload['report_name']}",
        "",
        f"Created at: `{payload['created_at']}`",
        "",
        "| window | candidate | rule | skipped | trades | avg R | max DD | profit factor |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for window in payload["windows"]:
        for candidate in dict(window)["candidates"]:
            for rule in dict(candidate)["rules"]:
                metrics = dict(dict(rule)["metrics"])
                lines.append(
                    "| "
                    f"{dict(window)['name']} | "
                    f"{dict(candidate)['candidate_name']} | "
                    f"{dict(rule)['name']} | "
                    f"{dict(rule)['skipped_row_count']} | "
                    f"{metrics['trade_count']} | "
                    f"{metrics['average_r']:.4f} | "
                    f"{metrics['max_drawdown_pct']:.2%} | "
                    f"{metrics['profit_factor']:.4f} |"
                )
    lines.extend(
        [
            "",
            "Research-only sensitivity screen. Full replay is required before any promotion.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_config(config: SelectedTradeAbstentionConfig) -> None:
    if not config.windows:
        raise SelectedTradeAbstentionError("windows must not be empty")
    if not config.rules:
        raise SelectedTradeAbstentionError("rules must not be empty")


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SelectedTradeAbstentionError(f"missing JSON input: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SelectedTradeAbstentionError(f"JSON input must be an object: {path}")
    return payload


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _expected_r_confidence(expected_r: float) -> float:
    return min(1.0, max(0.01, expected_r))


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_selected_trade_abstention_report(
        SelectedTradeAbstentionConfig.from_path(args.config)
    )
    for window in payload["windows"]:
        for candidate in dict(window)["candidates"]:
            for rule in dict(candidate)["rules"]:
                metrics = dict(dict(rule)["metrics"])
                print(
                    f"{dict(window)['name']} {dict(candidate)['candidate_name']} "
                    f"{dict(rule)['name']}: trades={metrics['trade_count']} "
                    f"avg_r={metrics['average_r']:.4f} "
                    f"max_dd={metrics['max_drawdown_pct']:.2%}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
