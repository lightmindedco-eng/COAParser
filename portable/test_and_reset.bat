@echo off
REM Complete test and cleanup for COAParser
REM This script will clear cache and re-parse the test file

setlocal enabledelayedexpansion

echo ============================================================
echo COAParser - Complete Reset & Test
echo ============================================================
echo.

REM Clear cache globally
echo [1/3] Clearing Python bytecode cache everywhere...
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" (
        rd /s /q "%%d" 2>nul
    )
)
echo ✓ Cache cleared
echo.

REM Clear previous output
echo [2/3] Clearing previous output files...
if exist "Output\*.txt" del /q "Output\*.txt" 2>nul
if exist "portable\Output\*.txt" del /q "portable\Output\*.txt" 2>nul
echo ✓ Previous outputs cleared
echo.

REM Run fresh parse on test PDF
echo [3/3] Parsing test PDFs fresh (no cache)...
set PYTHON_CMD=python
if exist "python.exe" set PYTHON_CMD="python.exe"
if exist "python3.exe" set PYTHON_CMD="python3.exe"

echo Using Python: !PYTHON_CMD!
echo.
echo Parsing: 0000324224.PDF
!PYTHON_CMD! -B diagnose.py
echo.

echo Parsing: 1A40E010002CF89000010613.pdf (from portable Input)
cd portable
!PYTHON_CMD! -B -c "from src.parser import COAParser; from pathlib import Path; import shutil; shutil.rmtree('__pycache__', ignore_errors=True); shutil.rmtree('src/__pycache__', ignore_errors=True); shutil.rmtree('src/parsers/__pycache__', ignore_errors=True); shutil.rmtree('src/core/__pycache__', ignore_errors=True); shutil.rmtree('src/gui/__pycache__', ignore_errors=True); r = COAParser().parse_file(Path('Input/1A40E010002CF89000010613.pdf').resolve() if Path('Input/1A40E010002CF89000010613.pdf').exists() else Path('../data/training/0000324224.PDF'), 'Output'); print(Path(r.output_path).read_text() if r.output_path else 'No output generated')"
cd ..
echo.

echo ============================================================
echo TEST COMPLETE
echo ============================================================
echo Output files should now show proper compound extraction.
echo Check: Output\0000324224.txt and portable\Output\*.txt
echo.
pause
