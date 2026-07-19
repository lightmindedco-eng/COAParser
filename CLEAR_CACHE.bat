@echo off
REM Quick cache clear and launcher re-run

echo Clearing Python cache...
for /d /r . %%d in (__pycache__) do rd /s /q "%%d" 2>nul

echo Clearing output files...
del /q Output\*.txt 2>nul
del /q portable\Output\*.txt 2>nul

echo.
echo Cache cleared. Now run the launcher fresh:
echo - Main: launcher.bat
echo - Portable: portable\launcher.bat
echo.
pause
