#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python docs/scripts/install_deps.py --with-dev

if [[ ! -f ".env" ]]; then
  cp .env.example .env
fi

python main.py --allow-cwd --no-auth --transport stdio
