#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.data.binance_order_book \
  --config configs/ct158-binance-order-book-forward-snapshot.json
