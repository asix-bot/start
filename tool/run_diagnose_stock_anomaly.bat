@echo off
chcp 866 >nul
cd /d "%~dp0"
setlocal

set "PYTHON=C:\Python34\python.exe"

if not exist "%PYTHON%" (
    echo.
    echo Ошибка: не найден Python по пути %PYTHON%
    echo Поправь путь в строке set "PYTHON=..." в начале этого файла.
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Использование: артикул1:ожидаемый_остаток1 артикул2:ожидаемый_остаток2 и так далее
    echo Пример: diagnose_stock_anomaly.py 5481ки:57 8814ки:62 6616ки:59
    pause
    exit /b 1
)

%PYTHON% diagnose_stock_anomaly.py %*
echo.
echo Результат сохранён локально и запушен на GitHub - смотри лог в репозитории.
pause
endlocal
exit /b 0
