#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_ROOT="${1:-$PROJECT_ROOT/backups}"
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_ROOT"

ARCHIVE="$BACKUP_ROOT/filesystem-mcp-server_$TS.tar.gz"

cd "$PROJECT_ROOT"
INCLUDE_PATHS=()
for p in .env .fastmcp_storage debug.log fastmcp.log; do
  if [[ -e "$p" ]]; then
    INCLUDE_PATHS+=("$p")
  fi
done

if [[ ${#INCLUDE_PATHS[@]} -eq 0 ]]; then
  echo "Nothing to back up. Expected one of: .env, .fastmcp_storage, debug.log, fastmcp.log"
  exit 1
fi

tar -czf "$ARCHIVE" "${INCLUDE_PATHS[@]}"

sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
echo "Backup created: $ARCHIVE"
