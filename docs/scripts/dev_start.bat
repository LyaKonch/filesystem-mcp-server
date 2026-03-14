@echo off
setlocal

set PROJECT_ROOT=%~dp0..\..
cd /d "%PROJECT_ROOT%"
set VENV_PY=.venv\Scripts\python.exe

if not exist "%VENV_PY%" (
  py -3.13 -m venv .venv
  if errorlevel 1 exit /b 1
)

"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_PY%" .\docs\scripts\install_deps.py --with-dev
if errorlevel 1 exit /b 1

if not exist ".env" (
  copy .env.example .env >nul
)

"%VENV_PY%" .\main.py --allow-cwd --no-auth --transport stdio
if errorlevel 1 exit /b 1
