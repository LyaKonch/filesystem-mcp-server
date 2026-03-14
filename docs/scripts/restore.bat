@echo off
setlocal

if "%~1"=="" (
  echo Usage: docs\scripts\restore.bat ^<backup-archive.zip^>
  exit /b 1
)

set ARCHIVE=%~1
set PROJECT_ROOT=%~dp0..\..

if not exist "%ARCHIVE%" (
  echo Archive not found: %ARCHIVE%
  exit /b 1
)

if /I "%~x1"==".sha256" (
  echo Expected archive file, got checksum file: %ARCHIVE%
  exit /b 1
)

if /I not "%~x1"==".zip" (
  echo Unsupported archive format: %ARCHIVE%
  echo Expected .zip
  exit /b 1
)

set CHECKSUM_FILE=%ARCHIVE%.sha256
if not exist "%CHECKSUM_FILE%" goto :skip_checksum

powershell -NoProfile -Command "$expected=(Get-Content '%CHECKSUM_FILE%' -Raw).Trim().ToLower(); $actual=(Get-FileHash -Algorithm SHA256 '%ARCHIVE%').Hash.ToLower(); if($expected -ne $actual){ Write-Error 'Checksum mismatch'; exit 1 } else { Write-Host 'Checksum verification passed' }"
if errorlevel 1 exit /b 1
goto :after_checksum

:skip_checksum
echo Checksum file not found (%CHECKSUM_FILE%). Skipping checksum verification.

:after_checksum

powershell -NoProfile -Command "Expand-Archive -Path '%ARCHIVE%' -DestinationPath '%PROJECT_ROOT%' -Force"
if errorlevel 1 exit /b 1

echo Restore completed from: %ARCHIVE%
