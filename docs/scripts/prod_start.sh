#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

source .venv/bin/activate
python main.py --transport http --host 0.0.0.0 --port 8000 --persist
