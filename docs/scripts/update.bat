@echo off
setlocal

set PROJECT_ROOT=%~dp0..\..
set TARGET_REF=%1
if "%TARGET_REF%"=="" set TARGET_REF=develop
set VENV_PY=.venv\Scripts\python.exe

cd /d "%PROJECT_ROOT%"
git fetch --all
if errorlevel 1 exit /b 1
git checkout %TARGET_REF%
if errorlevel 1 exit /b 1
git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>nul
if errorlevel 1 (
	echo No upstream tracking for branch %TARGET_REF%. Skipping git pull.
) else (
	git pull --ff-only
	if errorlevel 1 exit /b 1
)

if not exist "%VENV_PY%" (
	py -3.13 -m venv .venv
	if errorlevel 1 exit /b 1
)

"%VENV_PY%" .\docs\scripts\install_deps.py --with-dev
if errorlevel 1 exit /b 1

"%VENV_PY%" -m ruff check .
if errorlevel 1 exit /b 1
"%VENV_PY%" -m mypy .
if errorlevel 1 exit /b 1

echo Update completed for ref: %TARGET_REF%
