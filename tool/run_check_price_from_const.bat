@echo off
if "%~1"=="" (
    echo Использование: run_check_price_from_const.bat ^<индекс_базы 1-4^>
    pause
    exit /b 1
)
cd /d "%~dp0"
python check_price_from_const.py %1
if not "%~2"=="/silent" pause
