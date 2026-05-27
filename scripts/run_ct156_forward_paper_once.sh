#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.paper_forward \
  --config configs/ct156-high-beta-dot-forward-paper-run.json
