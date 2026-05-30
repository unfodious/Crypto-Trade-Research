import importlib.util
import sys
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
