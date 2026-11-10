@echo off
setlocal
cd /d "%~dp0"
set "PROJECT_PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PROJECT_PYTHON=%~dp0.venv\Scripts\python.exe"
"%PROJECT_PYTHON%" -m waitress --listen=127.0.0.1:5000 run:app

