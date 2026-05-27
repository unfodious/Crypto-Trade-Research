#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.data.external_forward_features \
  --config configs/ct162-external-forward-features.json
