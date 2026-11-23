@echo off
setlocal
cd /d "%~dp0"
where pwsh.exe >nul 2>&1
if not errorlevel 1 (
    pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-compare.ps1" -CheckOnly WinUI
) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-compare.ps1" -CheckOnly WinUI
)
set "status=%ERRORLEVEL%"
echo.
if not "%status%"=="0" echo WinUI GUI verification stopped. Please send WinUI-Check-0-automation.json and .tree.txt if available.
echo Press any key to close.
pause >nul
exit /b %status%
