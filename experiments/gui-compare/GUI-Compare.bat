@echo off
setlocal
cd /d "%~dp0"
where pwsh.exe >nul 2>&1
if not errorlevel 1 (
  pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-compare.ps1" %*
) else (
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-compare.ps1" %*
)
set "status=%ERRORLEVEL%"
echo.
if not "%status%"=="0" echo Comparison stopped with error %status%. See the saved run log for details.
echo Press any key to close.
pause >nul
exit /b %status%
