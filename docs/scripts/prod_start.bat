@echo off
setlocal

set PROJECT_ROOT=%~dp0..\..
cd /d "%PROJECT_ROOT%"
set VENV_PY=.venv\Scripts\python.exe

if not exist "%VENV_PY%" (
	echo Virtual environment not found. Run docs\scripts\dev_start.bat first.
	exit /b 1
)

"%VENV_PY%" .\main.py --transport http --host 0.0.0.0 --port 8000 --persist
if errorlevel 1 exit /b 1
