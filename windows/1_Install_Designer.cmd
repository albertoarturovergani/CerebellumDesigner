@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0CerebellumDesigner.ps1" -Action Install %*
set "cd_exit_code=%errorlevel%"
pause
exit /b %cd_exit_code%
