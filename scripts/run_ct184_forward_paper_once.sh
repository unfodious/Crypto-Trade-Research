#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.paper_forward \
  --config configs/ct184-adaptive-sizing-forward-paper-run.json
