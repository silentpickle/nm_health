#!/usr/bin/env bash
# The one gate: pre-commit runs it on every commit and CI runs it on every push. Any failure blocks.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check .
uv run ruff format --check .
uv run mypy nm_health tests
uv run python scripts/complexity.py
uv run shellcheck --severity=style scripts/*.sh
npm run --silent check
uv run pytest -q
