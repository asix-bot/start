@echo off
chcp 866 >nul
cd /d "%~dp0"
set "PYTHON=C:\Python34\python.exe"
if "%~1"=="" (
    echo Использование: run_check_price_from_const.bat ^<индекс_базы 1-4^>
    pause
    exit /b 1
)
%PYTHON% check_price_from_const.py %1
if not "%~2"=="/silent" pause
