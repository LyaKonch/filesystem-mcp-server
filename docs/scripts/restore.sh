#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash docs/scripts/restore.sh <backup-archive.tar.gz>"
  exit 1
fi

ARCHIVE="$1"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Archive not found: $ARCHIVE"
  exit 1
fi

if [[ "$ARCHIVE" == *.sha256 ]]; then
  echo "Expected archive file, got checksum file: $ARCHIVE"
  exit 1
fi

if [[ "$ARCHIVE" != *.tar.gz && "$ARCHIVE" != *.tgz ]]; then
  echo "Unsupported archive format: $ARCHIVE"
  echo "Expected .tar.gz or .tgz"
  exit 1
fi

CHECKSUM_FILE="$ARCHIVE.sha256"
if [[ -f "$CHECKSUM_FILE" ]]; then
  echo "Verifying checksum using: $CHECKSUM_FILE"
  sha256sum -c "$CHECKSUM_FILE"
else
  echo "Checksum file not found ($CHECKSUM_FILE). Skipping checksum verification."
fi

cd "$PROJECT_ROOT"
tar -xzf "$ARCHIVE"
echo "Restore completed from: $ARCHIVE"
