@echo off
setlocal

REM One-command launcher for Windows.
REM Runs PowerShell script with ExecutionPolicy bypass to avoid policy issues.

set SCRIPT_DIR=%~dp0scripts
set PS_SCRIPT=%SCRIPT_DIR%\run.ps1

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [neurofence] Failed with exit code %EXIT_CODE%.
  echo [neurofence] Tip: run ^"docker compose logs -f api^" to inspect.
)

exit /b %EXIT_CODE%
