#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.data.binance_crowding \
  --config configs/ct151-binance-crowding-forward-snapshot.json
