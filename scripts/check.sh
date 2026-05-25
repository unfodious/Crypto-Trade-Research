#!/usr/bin/env sh
set -eu

python -m pytest
ruff check .
ruff format --check .
