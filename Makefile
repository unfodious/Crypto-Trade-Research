.PHONY: install test lint format check

install:
	uv sync --extra dev --extra research

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test
