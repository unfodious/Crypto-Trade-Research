#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.data.hyperliquid_watchlist \
  --config configs/ct134-hyperliquid-whale-watchlist.json \
  --iterations 1 \
  --poll-interval-seconds 0 \
  --skip-fills
