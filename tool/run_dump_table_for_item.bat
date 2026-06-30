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

if "%~3"=="" (
    echo Использование: dump_table_for_item.py индекс_базы-1-4 таблица артикул_без_суффикса
    echo Пример: dump_table_for_item.py 2 RG10737 4241
    pause
    exit /b 1
)

%PYTHON% dump_table_for_item.py %*
echo.
echo Результат сохранён локально и запушен на GitHub - смотри лог в репозитории.
pause
endlocal
exit /b 0
