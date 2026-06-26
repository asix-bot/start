@echo off
chcp 866 >nul
cd /d "%~dp0"
setlocal

set "PYTHON=C:\Python34\python.exe"

if not exist "%PYTHON%" (
    echo.
    echo ОШИБКА: не найден Python по пути %PYTHON%
    echo Поправь путь в строке set "PYTHON=..." в начале этого файла.
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Использование: diagnose_stock.py - индекс_базы 1-4, артикул_без_суффикса
    echo Пример: diagnose_stock.py 3 38520
    pause
    exit /b 1
)

%PYTHON% diagnose_stock.py %*
echo.
echo Результат сохранён локально и - если настроен токен GitHub - запушен
echo в репозиторий, можно скачать без скриншотов терминала.
pause
endlocal
exit /b 0
