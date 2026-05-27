#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.data.binance_liquidations \
  --config configs/ct160-binance-liquidations-forward-snapshot.json
