import importlib.util
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path


def test_binance_spot_klines_timestamp_normalizes_millis_and_micros() -> None:
    script_path = Path("scripts/download_binance_spot_klines.py")
    spec = importlib.util.spec_from_file_location("download_binance_spot_klines", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["download_binance_spot_klines"] = module
    spec.loader.exec_module(module)

    assert module._binance_timestamp("1719792000000") == datetime(2024, 7, 1, tzinfo=UTC)
    assert module._binance_timestamp("1735689600000000") == datetime(2025, 1, 1, tzinfo=UTC)


def test_build_spot_klines_dataset_supports_custom_period(tmp_path: Path) -> None:
    script_path = Path("scripts/download_binance_spot_klines.py")
    spec = importlib.util.spec_from_file_location("download_binance_spot_klines", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["download_binance_spot_klines"] = module
    spec.loader.exec_module(module)

    cache_dir = tmp_path / "cache"
    output_dir = tmp_path / "out"
    cache_dir.mkdir()
    output_dir.mkdir()

    def fake_download_monthly_zip(
        symbol: str, period: str, year: int, month: int, cache_path: Path
    ) -> Path:
        path = cache_path / f"{symbol}-{period}-{year}-{month:02d}.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                f"{symbol}-{period}-{year}-{month:02d}.csv",
                ",".join(
                    [
                        "1735689600000",
                        "1.0",
                        "1.2",
                        "0.8",
                        "1.1",
                        "100.0",
                        "1735693200000",
                    ]
                ),
            )
        return path

    module._download_monthly_zip = fake_download_monthly_zip

    manifest_path = module.build_spot_klines_dataset(
        symbols=["BTCUSDT"],
        start=module._parse_timestamp("2025-01-01T00:00:00Z"),
        end=module._parse_timestamp("2025-01-02T00:00:00Z"),
        period="30m",
        dataset_name="ct_test_spot_30m",
        output_dir=output_dir,
        cache_dir=cache_dir,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["period"] == "30m"
    assert manifest["source"] == "binance-data-vision-spot-monthly-klines-30m"
    assert manifest["row_count"] == 1
