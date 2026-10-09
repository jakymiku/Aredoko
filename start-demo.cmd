@echo off
cd /d "%~dp0"
python app\server.py --open
if errorlevel 1 pause
