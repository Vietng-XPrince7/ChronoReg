@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-advisor.ps1" %*
exit /b %errorlevel%
