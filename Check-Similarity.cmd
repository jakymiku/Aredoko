@echo off
cd /d "%~dp0"
python tools\check_similarity_local.py --native %*
exit /b %errorlevel%
