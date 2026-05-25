#!/usr/bin/env python
"""Generate sample after-the-fact labels from the committed fake market fixture."""

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.data.ingestion import MarketDatasetConfig, generate_market_dataset
from crypto_trade_research.labels import LabelConfig, generate_trade_labels


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label-set-version", required=True)
    parser.add_argument("--horizon-bars", type=int, required=True)
    parser.add_argument("--side", choices=["long", "short"], required=True)
    parser.add_argument("--stop-loss-pct", type=float, required=True)
    parser.add_argument("--target-pct", type=float, required=True)
    parser.add_argument("--cost-pct", type=float, required=True)
    parser.add_argument("--flat-threshold-pct", type=float, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        manifest = generate_market_dataset(
            MarketDatasetConfig(
                source_csv=args.source_csv,
                output_dir=Path(tmp_dir),
                dataset_name="sample_label_source",
                generator_version="sample.labels.source.v1",
            )
        )
        source_rows = pq.read_table(manifest.cleaned_path).to_pylist()

    frame = generate_trade_labels(
        source_rows,
        LabelConfig(
            label_set_version=args.label_set_version,
            horizon_bars=args.horizon_bars,
            side=args.side,
            stop_loss_pct=args.stop_loss_pct,
            target_pct=args.target_pct,
            cost_pct=args.cost_pct,
            flat_threshold_pct=args.flat_threshold_pct,
        ),
    )

    labels_path = args.output_dir / "labels.parquet"
    label_manifest_path = args.output_dir / "label_manifest.json"
    pq.write_table(pa.Table.from_pylist(frame.rows), labels_path)
    label_manifest_path.write_text(
        json.dumps(asdict(frame.manifest), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(label_manifest_path)


if __name__ == "__main__":
    main()
