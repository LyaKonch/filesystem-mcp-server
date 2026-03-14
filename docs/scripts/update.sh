#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_REF="${1:-develop}"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"

cd "$PROJECT_ROOT"
git fetch --all
git checkout "$TARGET_REF"
if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
	git pull --ff-only
else
	echo "No upstream tracking for branch $TARGET_REF. Skipping git pull."
fi

if [[ ! -x "$VENV_PY" ]]; then
	python3 -m venv "$PROJECT_ROOT/.venv"
fi

"$VENV_PY" "$PROJECT_ROOT/docs/scripts/install_deps.py" --with-dev

"$VENV_PY" -m ruff check .
"$VENV_PY" -m mypy .

echo "Update completed for ref: $TARGET_REF"
