#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.forward_filter_diagnostics \
  --config configs/ct167-forward-filter-diagnostics.json
