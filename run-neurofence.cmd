@echo off
setlocal

REM One-command NeuroFence runner (Windows)

set SCRIPT_DIR=%~dp0scripts
set PS_SCRIPT=%SCRIPT_DIR%\run.ps1

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
exit /b %ERRORLEVEL%
