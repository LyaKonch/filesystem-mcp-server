@echo off
setlocal

set PROJECT_ROOT=%~dp0..\..
set BACKUP_ROOT=%1
if "%BACKUP_ROOT%"=="" set BACKUP_ROOT=%PROJECT_ROOT%\backups

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
if not exist "%BACKUP_ROOT%" mkdir "%BACKUP_ROOT%"

set ARCHIVE=%BACKUP_ROOT%\filesystem-mcp-server_%TS%.zip

powershell -NoProfile -Command "$items=@(); foreach($p in @('%PROJECT_ROOT%\\.env','%PROJECT_ROOT%\\.fastmcp_storage','%PROJECT_ROOT%\\debug.log','%PROJECT_ROOT%\\fastmcp.log')){ if(Test-Path $p){ $items += $p } }; if($items.Count -eq 0){ Write-Error 'Nothing to back up. Expected one of: .env, .fastmcp_storage, debug.log, fastmcp.log'; exit 1 }; Compress-Archive -Path $items -DestinationPath '%ARCHIVE%' -Force"
if errorlevel 1 exit /b 1

powershell -NoProfile -Command "$h=(Get-FileHash -Algorithm SHA256 '%ARCHIVE%').Hash.ToLower(); [System.IO.File]::WriteAllText('%ARCHIVE%.sha256',$h)"
if errorlevel 1 exit /b 1

echo Backup created: %ARCHIVE%
