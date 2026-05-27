"""Build point-in-time external forward features from research-only snapshot streams."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "research.external_forward_features.v1"
GENERATOR_NAME = "crypto_trade_research.external_forward_features"


class ExternalForwardFeatureError(ValueError):
    """Raised when external forward feature generation fails validation."""


@dataclass(frozen=True, slots=True)
class ExternalForwardFeatureConfig:
    source_root: Path
    output_dir: Path
    dataset_prefix: str
    generator_version: str
    symbols: tuple[str, ...]
    crowding_prefix: str
    order_book_prefix: str
    liquidation_prefix: str
    generated_at: datetime | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExternalForwardFeatureConfig:
        return cls(
            source_root=Path(str(payload.get("source_root", "."))),
            output_dir=Path(str(payload["output_dir"])),
            dataset_prefix=str(payload["dataset_prefix"]),
            generator_version=str(payload["generator_version"]),
            symbols=tuple(str(symbol).upper() for symbol in payload["symbols"]),
            crowding_prefix=str(payload["crowding_prefix"]),
            order_book_prefix=str(payload["order_book_prefix"]),
            liquidation_prefix=str(payload["liquidation_prefix"]),
            generated_at=_parse_timestamp_optional(payload.get("generated_at")),
        )

    @classmethod
    def from_path(cls, path: Path) -> ExternalForwardFeatureConfig:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class ExternalForwardFeatureManifest:
    schema_version: str
    dataset_name: str
    generator_name: str
    generator_version: str
    generated_at: str
    row_count: int
    crowding_snapshot_count: int
    order_book_snapshot_count: int
    liquidation_snapshot_count: int
    symbols: tuple[str, ...]
    features_path: Path
    manifest_path: Path
    features_sha256: str
    warnings: tuple[str, ...]


def build_external_forward_features(
    config: ExternalForwardFeatureConfig,
) -> ExternalForwardFeatureManifest:
    """Build a narrow point-in-time feature table from external forward snapshots."""

    _validate_config(config)
    generated_at = config.generated_at or datetime.now(UTC)
    dataset_name = f"{config.dataset_prefix}_{_compact_timestamp(generated_at)}"
    dataset_dir = config.output_dir / dataset_name
    warnings: list[str] = []
    rows: list[dict[str, object]] = []

    crowding_manifests = _find_manifests(config.source_root, config.crowding_prefix)
    order_book_manifests = _find_manifests(config.source_root, config.order_book_prefix)
    liquidation_manifests = _find_manifests(config.source_root, config.liquidation_prefix)

    for manifest_path in crowding_manifests:
        try:
            rows.extend(_build_crowding_rows(config, manifest_path))
        except Exception as exc:  # noqa: BLE001 - keep other snapshots usable.
            warnings.append(f"{manifest_path} crowding feature build failed: {exc}")

    for manifest_path in order_book_manifests:
        try:
            rows.extend(_build_order_book_rows(config, manifest_path))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{manifest_path} order-book feature build failed: {exc}")

    for manifest_path in liquidation_manifests:
        try:
            rows.extend(_build_liquidation_rows(config, manifest_path))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{manifest_path} liquidation feature build failed: {exc}")

    if not rows:
        raise ExternalForwardFeatureError("no external forward feature rows were generated")

    features_path = dataset_dir / "clean" / "external_forward_features.parquet"
    manifest_path = dataset_dir / "manifest.json"
    _write_rows(features_path, rows)
    manifest = ExternalForwardFeatureManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=dataset_name,
        generator_name=GENERATOR_NAME,
        generator_version=config.generator_version,
        generated_at=_format_timestamp(generated_at),
        row_count=len(rows),
        crowding_snapshot_count=len(crowding_manifests),
        order_book_snapshot_count=len(order_book_manifests),
        liquidation_snapshot_count=len(liquidation_manifests),
        symbols=tuple(sorted(set(str(row["symbol"]) for row in rows))),
        features_path=features_path,
        manifest_path=manifest_path,
        features_sha256=_file_sha256(features_path),
        warnings=tuple(warnings),
    )
    _write_manifest(manifest, config)
    _write_run_summary(config, manifest)
    return manifest


def _build_crowding_rows(
    config: ExternalForwardFeatureConfig,
    manifest_path: Path,
) -> list[dict[str, object]]:
    manifest = _read_json(manifest_path)
    current_rows = _read_manifest_table(config, manifest, "current_open_interest_path")
    hist_rows = _read_manifest_table(config, manifest, "open_interest_hist_path")
    global_rows = _read_manifest_table(config, manifest, "global_long_short_path")
    top_position_rows = _read_manifest_table(config, manifest, "top_long_short_position_path")
    top_account_rows = _read_manifest_table(config, manifest, "top_long_short_account_path")
    by_symbol: dict[str, dict[str, object]] = {}
    symbols = set(config.symbols)

    for row in current_rows:
        symbol = _symbol(row)
        if symbol in symbols:
            by_symbol.setdefault(symbol, _base_row("crowding", manifest, symbol))[
                "crowding_open_interest"
            ] = row.get("open_interest")
    for row in hist_rows:
        symbol = _symbol(row)
        if symbol in symbols:
            feature_row = by_symbol.setdefault(symbol, _base_row("crowding", manifest, symbol))
            feature_row["crowding_sum_open_interest"] = row.get("sum_open_interest")
            feature_row["crowding_sum_open_interest_value"] = row.get("sum_open_interest_value")
    for row in global_rows:
        symbol = _symbol(row)
        if symbol in symbols:
            by_symbol.setdefault(symbol, _base_row("crowding", manifest, symbol))[
                "global_long_short_ratio"
            ] = row.get("long_short_ratio")
    for row in top_position_rows:
        symbol = _symbol(row)
        if symbol in symbols:
            by_symbol.setdefault(symbol, _base_row("crowding", manifest, symbol))[
                "top_trader_position_long_short_ratio"
            ] = row.get("long_short_ratio")
    for row in top_account_rows:
        symbol = _symbol(row)
        if symbol in symbols:
            by_symbol.setdefault(symbol, _base_row("crowding", manifest, symbol))[
                "top_trader_account_long_short_ratio"
            ] = row.get("long_short_ratio")
    return [_complete_row(row) for row in by_symbol.values()]


def _build_order_book_rows(
    config: ExternalForwardFeatureConfig,
    manifest_path: Path,
) -> list[dict[str, object]]:
    manifest = _read_json(manifest_path)
    rows = _read_manifest_table(config, manifest, "summary_path")
    feature_rows: list[dict[str, object]] = []
    symbols = set(config.symbols)
    for row in rows:
        symbol = _symbol(row)
        if symbol not in symbols:
            continue
        feature_row = _base_row("order_book", manifest, symbol)
        feature_row.update(
            {
                "order_book_spread_bps": row.get("spread_bps"),
                "order_book_bid_notional_total": row.get("bid_notional_total"),
                "order_book_ask_notional_total": row.get("ask_notional_total"),
                "order_book_notional_imbalance": row.get("notional_imbalance"),
                "order_book_largest_bid_notional": row.get("largest_bid_notional"),
                "order_book_largest_bid_distance_bps": row.get("largest_bid_distance_bps"),
                "order_book_largest_ask_notional": row.get("largest_ask_notional"),
                "order_book_largest_ask_distance_bps": row.get("largest_ask_distance_bps"),
            }
        )
        feature_rows.append(_complete_row(feature_row))
    return feature_rows


def _build_liquidation_rows(
    config: ExternalForwardFeatureConfig,
    manifest_path: Path,
) -> list[dict[str, object]]:
    manifest = _read_json(manifest_path)
    rows = _read_manifest_table(config, manifest, "liquidations_path")
    symbols = set(config.symbols)
    grouped: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "event_count": 0.0,
            "notional_total": 0.0,
            "long_notional": 0.0,
            "short_notional": 0.0,
        }
    )
    for row in rows:
        symbol = _symbol(row)
        if symbol not in symbols:
            continue
        notional = float(row.get("notional") or 0.0)
        grouped[symbol]["event_count"] += 1
        grouped[symbol]["notional_total"] += notional
        if row.get("liquidation_direction") == "long_liquidation":
            grouped[symbol]["long_notional"] += notional
        elif row.get("liquidation_direction") == "short_liquidation":
            grouped[symbol]["short_notional"] += notional

    feature_rows: list[dict[str, object]] = []
    for symbol in sorted(symbols):
        group = grouped[symbol]
        denominator = group["long_notional"] + group["short_notional"]
        imbalance = (
            0.0
            if denominator == 0
            else (group["long_notional"] - group["short_notional"]) / denominator
        )
        feature_row = _base_row("liquidations", manifest, symbol)
        feature_row["source_available_at"] = _parse_manifest_time(
            manifest.get("capture_ended_at") or manifest.get("generated_at")
        )
        feature_row.update(
            {
                "liquidation_event_count": int(group["event_count"]),
                "liquidation_notional_total": group["notional_total"],
                "long_liquidation_notional": group["long_notional"],
                "short_liquidation_notional": group["short_notional"],
                "liquidation_notional_imbalance": imbalance,
            }
        )
        feature_rows.append(_complete_row(feature_row))
    return feature_rows


def _base_row(
    feature_family: str,
    manifest: dict[str, object],
    symbol: str,
) -> dict[str, object]:
    source_available_at = _parse_manifest_time(manifest.get("generated_at"))
    return {
        "schema_version": SCHEMA_VERSION,
        "feature_family": feature_family,
        "source_dataset_name": str(manifest.get("dataset_name", "")),
        "symbol": symbol,
        "source_available_at": source_available_at,
    }


def _complete_row(row: dict[str, object]) -> dict[str, object]:
    defaults: dict[str, object] = {
        "crowding_open_interest": None,
        "crowding_sum_open_interest": None,
        "crowding_sum_open_interest_value": None,
        "global_long_short_ratio": None,
        "top_trader_position_long_short_ratio": None,
        "top_trader_account_long_short_ratio": None,
        "order_book_spread_bps": None,
        "order_book_bid_notional_total": None,
        "order_book_ask_notional_total": None,
        "order_book_notional_imbalance": None,
        "order_book_largest_bid_notional": None,
        "order_book_largest_bid_distance_bps": None,
        "order_book_largest_ask_notional": None,
        "order_book_largest_ask_distance_bps": None,
        "liquidation_event_count": None,
        "liquidation_notional_total": None,
        "long_liquidation_notional": None,
        "short_liquidation_notional": None,
        "liquidation_notional_imbalance": None,
    }
    return {**defaults, **row}


def _find_manifests(source_root: Path, prefix: str) -> list[Path]:
    prefix_path = source_root / prefix
    parent = prefix_path.parent
    if not parent.exists():
        return []
    return sorted(parent.glob(f"{prefix_path.name}_*/manifest.json"))


def _read_manifest_table(
    config: ExternalForwardFeatureConfig,
    manifest: dict[str, object],
    field: str,
) -> list[dict[str, object]]:
    raw_path = manifest.get(field)
    if not raw_path:
        return []
    path = _resolve_source_path(config.source_root, str(raw_path))
    if not path.exists():
        raise ExternalForwardFeatureError(f"missing source parquet: {path}")
    return pq.read_table(path).to_pylist()


def _resolve_source_path(source_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return source_root / path


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ExternalForwardFeatureError(f"manifest must be an object: {path}")
    return payload


def _symbol(row: dict[str, object]) -> str:
    return str(row.get("symbol", "")).upper()


def _validate_config(config: ExternalForwardFeatureConfig) -> None:
    if not config.symbols:
        raise ExternalForwardFeatureError("symbols must not be empty")
    if config.generated_at is not None and config.generated_at.tzinfo is None:
        raise ExternalForwardFeatureError("generated_at must be timezone-aware")


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_manifest(
    manifest: ExternalForwardFeatureManifest,
    config: ExternalForwardFeatureConfig,
) -> None:
    payload = asdict(manifest)
    payload["features_path"] = str(manifest.features_path)
    payload["manifest_path"] = str(manifest.manifest_path)
    payload["source"] = {
        "source_root": str(config.source_root),
        "crowding_prefix": config.crowding_prefix,
        "order_book_prefix": config.order_book_prefix,
        "liquidation_prefix": config.liquidation_prefix,
        "notes": (
            "Rows are point-in-time external features derived from forward research snapshots. "
            "Liquidation features use capture_ended_at as source_available_at."
        ),
    }
    manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_run_summary(
    config: ExternalForwardFeatureConfig,
    manifest: ExternalForwardFeatureManifest,
) -> None:
    run_dir = config.output_dir / config.dataset_prefix
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "research.external_forward_features_run.v1",
        "generator_name": GENERATOR_NAME,
        "generator_version": config.generator_version,
        "created_at": _format_timestamp(datetime.now(UTC)),
        "latest_manifest_path": str(manifest.manifest_path),
        "latest_dataset_name": manifest.dataset_name,
        "latest_generated_at": manifest.generated_at,
        "row_count": manifest.row_count,
        "crowding_snapshot_count": manifest.crowding_snapshot_count,
        "order_book_snapshot_count": manifest.order_book_snapshot_count,
        "liquidation_snapshot_count": manifest.liquidation_snapshot_count,
        "symbols": list(manifest.symbols),
        "warnings": list(manifest.warnings),
        "notes": "Research-only feature table. No orders are submitted or modified.",
    }
    (run_dir / "external_forward_features_run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compact_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_manifest_time(value: object) -> datetime:
    if not value:
        raise ExternalForwardFeatureError("manifest timestamp is required")
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _parse_timestamp_optional(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ExternalForwardFeatureError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = build_external_forward_features(ExternalForwardFeatureConfig.from_path(args.config))
    print(manifest.manifest_path)


if __name__ == "__main__":
    main()
