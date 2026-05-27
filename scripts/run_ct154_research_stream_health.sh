#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

exec .venv/bin/python -m crypto_trade_research.research_stream_health --root .
