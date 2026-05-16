@echo off
setlocal
cd /d "%~dp0"
echo Starting AI Scientific Reviewer System...
echo Project folder: %CD%
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_web.ps1"
echo.
echo If the app did not open, check server_log.txt in this folder.
pause
