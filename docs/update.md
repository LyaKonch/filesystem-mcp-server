# Update and Rollback Guide

## 1. Scope

This document describes safe update procedure for `filesystem-mcp-server`, including rollback.

## 2. Pre-update checklist

1. Confirm target version/commit.
2. Notify stakeholders about maintenance window (if downtime is expected).
3. Create backups before any changes (see `docs/backup.md`).
4. Validate compatibility of:
   - Python version
   - `.env` variables
   - Redis availability (if enabled)

## 3. Update procedure (Linux)

```bash
cd /opt/filesystem-mcp-server
git fetch --all
git checkout <target-branch-or-tag>
git pull --ff-only
source .venv/bin/activate
pip install -e .
```

Restart service/process and verify startup logs.

## 4. Update procedure (Windows PowerShell)

```powershell
cd C:\services\filesystem-mcp-server
git fetch --all
git checkout <target-branch-or-tag>
git pull --ff-only
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Restart service/process and verify startup logs.

## 5. Post-update verification

- Service process is healthy.
- MCP endpoint responds.
- Core tool calls work (`list_files`, `read_file`, `get_system_resource_usage`).
- Auth flow works (if enabled).
- No critical errors in logs in first 5–10 minutes.

## 6. Rollback procedure

If update fails:

1. Stop service.
2. Checkout previous known-good commit/tag.
3. Reinstall dependencies (if changed).
4. Restore previous `.env` and storage backup if required.
5. Start service and verify health checks.

Linux example:

```bash
cd /opt/filesystem-mcp-server
git checkout <previous-tag>
source .venv/bin/activate
pip install -e .
# or
uv sync
```

Windows example:

```powershell
cd C:\services\filesystem-mcp-server
git checkout <previous-tag>
.\.venv\Scripts\Activate.ps1
pip install -e .
# or
uv sync
```

## 7. Downtime and risk guidance

- For non-breaking updates, rollout can be done with short restart window.
- For auth/storage changes, schedule maintenance and ensure backup restore plan is tested.
- Always keep at least one known-good deployment artifact ready for quick rollback.
