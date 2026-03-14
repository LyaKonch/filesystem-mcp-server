@echo off
setlocal

set PROJECT_ROOT=%~dp0..\..
set TARGET_BRANCH=%1
if "%TARGET_BRANCH%"=="" set TARGET_BRANCH=release
set VENV_PY=.venv\Scripts\python.exe

cd /d "%PROJECT_ROOT%"
git fetch --all
if errorlevel 1 exit /b 1
git checkout %TARGET_BRANCH%
if errorlevel 1 exit /b 1
git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>nul
if errorlevel 1 (
	echo No upstream tracking for branch %TARGET_BRANCH%. Skipping git pull.
) else (
	git pull --ff-only
	if errorlevel 1 exit /b 1
)

if not exist "%VENV_PY%" (
	py -3.13 -m venv .venv
	if errorlevel 1 exit /b 1
)

"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_PY%" .\docs\scripts\install_deps.py --with-dev
if errorlevel 1 exit /b 1

echo Deployment completed for branch: %TARGET_BRANCH%
