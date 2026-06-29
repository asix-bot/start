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
    echo Использование: артикул1:цена1:себестоимость1 артикул2:цена2 и так далее
    echo Пример: find_price_cost_field.py 100ш:2220:1350 941ш:2360
    pause
    exit /b 1
)

%PYTHON% find_price_cost_field.py %*
echo.
echo Результат сохранён локально и запушен на GitHub - смотри лог в репозитории.
pause
endlocal
exit /b 0
