@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ============================================================
echo COAParser (Portable) - First Time Setup
echo ============================================================
echo.

set "BOOTSTRAP_KIND="
set "BOOTSTRAP_PY="

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "BOOTSTRAP_KIND=python"
    set "BOOTSTRAP_PY=%SCRIPT_DIR%.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set "BOOTSTRAP_KIND=python"
    set "BOOTSTRAP_PY=%SCRIPT_DIR%venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%python.exe" (
    set "BOOTSTRAP_KIND=python"
    set "BOOTSTRAP_PY=%SCRIPT_DIR%python.exe"
) else if exist "%SCRIPT_DIR%python3.exe" (
    set "BOOTSTRAP_KIND=python"
    set "BOOTSTRAP_PY=%SCRIPT_DIR%python3.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 set "BOOTSTRAP_KIND=py"
)

if not defined BOOTSTRAP_KIND (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "BOOTSTRAP_KIND=python"
        set "BOOTSTRAP_PY=python"
    )
)

if not defined BOOTSTRAP_KIND (
    echo ERROR: Python was not found.
    echo Install Python 3.12+ and run this script again.
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    echo Creating portable virtual environment...
    if /I "%BOOTSTRAP_KIND%"=="py" (
        py -3 -m venv "%SCRIPT_DIR%.venv"
    ) else (
        "%BOOTSTRAP_PY%" -m venv "%SCRIPT_DIR%.venv"
    )

    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        echo.
        pause
        exit /b 1
    )
) else (
    echo Portable virtual environment already exists.
)

set "VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ERROR: Virtual environment Python not found at:
    echo %VENV_PY%
    echo.
    pause
    exit /b 1
)

echo.
echo Installing/updating dependencies...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    echo.
    pause
    exit /b 1
)

"%VENV_PY%" -m pip install -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
    echo ERROR: Failed to install requirements.
    echo.
    pause
    exit /b 1
)

echo.
echo Setup complete. Launching COAParser...
call "%SCRIPT_DIR%launcher.bat"

exit /b %errorlevel%