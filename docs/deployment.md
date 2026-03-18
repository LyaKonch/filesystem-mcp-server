# Production Deployment Guide

## 1. Scope

This document describes production deployment of `filesystem-mcp-server` for Linux and Windows environments.

## 2. Infrastructure requirements

### Hardware (minimum)
- CPU: 2 vCPU
- RAM: 4 GB
- Disk: 20 GB SSD
- Network: stable outbound access for dependency installation and optional GitHub OAuth callbacks

### Operating system
- Linux: Ubuntu 22.04 LTS or newer
- Windows Server: 2019 or newer

### Required software
- Python 3.13+
- Git
- Reverse proxy (recommended): Nginx/Caddy (Linux) or IIS reverse proxy (Windows)
- Optional: Redis 7+ if persistent session storage is enabled

## 3. Network and security baseline

- Expose only required port (`MCP_PORT`, default `8000`) to trusted networks.
- Use TLS termination at reverse proxy layer.
- Restrict file operations using `ALLOWED_ROOTS`.
- Do not run service as administrator/root unless explicitly required.

## 4. Deployment steps (Linux)

```bash
git clone <repository-url>
cd filesystem-mcp-server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
cp .env.example .env
```

Set production values in `.env`:
- `AUTH_ENABLED=true`
- `USE_PERSISTENT_STORAGE=true`
- `STORAGE_ENCRYPTION_KEY=<value>`
- `JWT_SIGNING_KEY=<value>`
- `ALLOWED_ROOTS=<strict list of directories>`

Start server:

```bash
source .venv/bin/activate
python main.py --transport http --host 0.0.0.0 --port 8000 --persist
```

## 5. Deployment steps (Windows PowerShell)

```powershell
git clone <repository-url>
cd filesystem-mcp-server
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
Copy-Item .env.example .env
```

Set production values in `.env` (same as Linux section), then start service:

```powershell
.\.venv\Scripts\Activate.ps1
python .\main.py --transport http --host 0.0.0.0 --port 8000 --persist
```

## 6. Database and storage notes

- This project does not use a relational database.
- State is kept in local storage and optionally Redis for persistent auth/session data.
- If Redis is used, ensure `REDIS_HOST` and `REDIS_PORT` are reachable from the app host.

## 7. Health verification checklist

After deployment, verify:
- Process is running and listening on configured host/port.
- Service responds to MCP endpoint (`/mcp` for HTTP transport setup).
- Tool calls work for allowed paths only.
- Logs contain startup line with transport and auth mode.

## 8. Recommended service wrappers

- Linux: `systemd` unit (example scripts in `docs/scripts`).
- Windows: Task Scheduler / NSSM service wrapper (example scripts in `docs/scripts`).
