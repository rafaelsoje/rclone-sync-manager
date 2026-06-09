@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

if "%~1"=="" (
    start "" powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run.ps1" gui
    exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run.ps1" %*
exit /b %ERRORLEVEL%
