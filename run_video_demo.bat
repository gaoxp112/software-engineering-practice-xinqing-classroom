@echo off
setlocal
cd /d "%~dp0"
set "PROJECT_PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PROJECT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined FFMPEG_EXE if exist "%~dp0.venv\Scripts\ffmpeg.exe" set "FFMPEG_EXE=%~dp0.venv\Scripts\ffmpeg.exe"
"%PROJECT_PYTHON%" scripts\run_video_demo.py %*
if errorlevel 1 pause
