#!/usr/bin/env python
"""Generate sample OHLCV features from the committed fake market fixture."""

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_trade_research.data.ingestion import MarketDatasetConfig, generate_market_dataset
from crypto_trade_research.features import FeatureConfig, generate_ohlcv_features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--feature-set-version", required=True)
    parser.add_argument("--rolling-window", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        manifest = generate_market_dataset(
            MarketDatasetConfig(
                source_csv=args.source_csv,
                output_dir=Path(tmp_dir),
                dataset_name="sample_feature_source",
                generator_version="sample.features.source.v1",
            )
        )
        source_rows = pq.read_table(manifest.cleaned_path).to_pylist()

    frame = generate_ohlcv_features(
        source_rows,
        FeatureConfig(
            feature_set_version=args.feature_set_version,
            rolling_window=args.rolling_window,
        ),
    )

    features_path = args.output_dir / "features.parquet"
    feature_manifest_path = args.output_dir / "feature_manifest.json"
    pq.write_table(pa.Table.from_pylist(frame.rows), features_path)
    feature_manifest_path.write_text(
        json.dumps(asdict(frame.manifest), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(feature_manifest_path)


if __name__ == "__main__":
    main()
