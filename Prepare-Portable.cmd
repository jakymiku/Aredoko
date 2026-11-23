@echo off
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\prepare-portable.ps1"
if errorlevel 1 echo Preparation failed. Check the log shown above.
pause
