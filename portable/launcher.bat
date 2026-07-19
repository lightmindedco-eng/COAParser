@echo off
setlocal
set "PYTHON_CMD=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_CMD=%~dp0venv\Scripts\python.exe"
if exist "%~dp0python.exe" set "PYTHON_CMD=%~dp0python.exe"
if exist "%~dp0python3.exe" set "PYTHON_CMD=%~dp0python3.exe"
"%PYTHON_CMD%" launcher.py
