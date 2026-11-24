@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0CerebellumDesigner.ps1" -Action Exports %*
set "cd_exit_code=%errorlevel%"
if not "%cd_exit_code%"=="0" pause
exit /b %cd_exit_code%
