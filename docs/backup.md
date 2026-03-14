# Backup and Restore Guide

## 1. Scope

This document defines backup strategy and operational procedures for `filesystem-mcp-server`.

## 2. Backup strategy

### Types
- Full backups: complete snapshot of critical data.
- Incremental backups: changed files since last backup.
- Differential backups: changed files since last full backup.

### Recommended frequency
- Full backup: daily.
- Incremental backup: every 4–6 hours.
- Config backup (`.env`, deployment configs): on each release/update.

### Retention and rotation
- Keep daily backups for 7 days.
- Keep weekly backups for 4 weeks.
- Keep monthly backups for 3 months.

## 3. What to back up

- Configuration files (`.env`, service configs).
- Local auth/session storage files (if disk-based persistence is enabled).
- Operational logs (`debug.log`, `fastmcp.log`) when required for incident analysis.
- Redis snapshots (if Redis persistence is enabled).

## 4. Backup procedures

### Linux
Use script:

```bash
bash docs/scripts/backup.sh /var/backups/filesystem-mcp-server
```

### Windows PowerShell
Use script:

```powershell
docs\scripts\backup.bat "D:\backups\filesystem-mcp-server"
```

## 5. Integrity verification

- Check archive creation status and file size.
- Validate checksum (`sha256`) for backup artifacts.
- Periodically run test restore into staging environment.
- Restore scripts automatically verify checksum when `<archive>.sha256` exists.
- Do not pass checksum files directly to restore scripts; always pass the archive file (`.tar.gz`/`.zip`).

## 6. Restore procedures

### Full restore (Linux)

```bash
bash docs/scripts/restore.sh /var/backups/filesystem-mcp-server/<backup-file.tar.gz>
```

### Full restore (Windows)

```powershell
docs\scripts\restore.bat "D:\backups\filesystem-mcp-server\<backup-file.zip>"
```

### Selective restore

- Extract only required files (`.env`, storage file, logs) into target paths.
- Restart service and verify startup/health.

## 7. Recovery testing cadence

- Run full restore test at least once per month.
- Validate service startup and tool calls after restore.
- Record restore time to maintain recovery objective tracking.
