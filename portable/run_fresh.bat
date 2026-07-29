@echo off
REM Script to clear Python cache and run the program fresh
setlocal enabledelayedexpansion

echo ============================================================
echo COAParser - Fresh Run (Cache Cleared)
echo ============================================================
echo.

REM Clear all __pycache__ directories
echo Clearing Python bytecode cache...
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" (
        echo Removing %%d
        rd /s /q "%%d" 2>nul
    )
)
echo Cache cleared.
echo.

REM Run the GUI launcher
echo Starting GUI launcher...
set "PYTHON_CMD=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_CMD=%~dp0venv\Scripts\python.exe"
if exist "%~dp0python.exe" set "PYTHON_CMD=%~dp0python.exe"
if exist "%~dp0python3.exe" set "PYTHON_CMD=%~dp0python3.exe"

echo Using Python: !PYTHON_CMD!
echo.

"!PYTHON_CMD!" launcher.py

if errorlevel 1 (
    echo.
    echo ERROR: Launcher failed with exit code %errorlevel%
    echo Please check the error message above.
)

pause
