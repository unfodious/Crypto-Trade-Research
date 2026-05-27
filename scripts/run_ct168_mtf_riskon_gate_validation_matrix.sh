#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.experiments.batch \
  --matrix configs/ct168-mtf-riskon-gate-validation-matrix.json
