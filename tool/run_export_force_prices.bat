@echo off
chcp 866 >nul
cd /d "%~dp0"

set "PYTHON=C:\Python34\python.exe"

if not exist "%PYTHON%" (
    echo.
    echo Error: Python not found at %PYTHON%
    echo Fix PYTHON= path at the top of this file.
    echo.
    pause
    exit /b 1
)

echo Force-recalc: ignoring price window and cache.
echo.
echo [%date% %time%] Updating scripts from GitHub...
%PYTHON% update_scripts.py
if errorlevel 1 (
    echo [%date% %time%] Script update failed, continuing with current files.
)

echo [%date% %time%] Deleting price_cache.json...
if exist price_cache.json del price_cache.json

echo [%date% %time%] Running export with forced price recalc...
%PYTHON% main.py --force-price-recalc
if errorlevel 1 (
    echo [%date% %time%] main.py failed.
    pause
    exit /b 1
)

echo [%date% %time%] Done.
pause
