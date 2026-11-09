#!/usr/bin/env bash
# Copyright (c) 2026 nm_health contributors
# Every check for the citymap package: Python (ruff, ruff format, mypy --strict, complexity, pytest), shell
# (shellcheck) and JavaScript (Prettier, ESLint, tsc, node --test). Any failure stops the run with a non-zero exit.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run python scripts/complexity.py
uv run shellcheck --severity=style scripts/*.sh
uv run pytest -q

if [ ! -d node_modules ]; then
  npm ci --no-audit --no-fund
fi
npm run --silent check
