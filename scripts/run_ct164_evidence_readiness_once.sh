#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.evidence_readiness \
  --config configs/ct164-evidence-readiness.json
