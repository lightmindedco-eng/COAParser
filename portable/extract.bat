@echo off
setlocal
set PYTHON_CMD=%~1
if "%PYTHON_CMD%"=="" set PYTHON_CMD=python
"%PYTHON_CMD%" app.py
