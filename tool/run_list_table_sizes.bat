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

if "%~2"=="" (
    echo Использование: list_table_sizes.py индекс_базы-1-4 префикс
    echo Пример: list_table_sizes.py 2 SC
    pause
    exit /b 1
)

%PYTHON% list_table_sizes.py %*
echo.
echo Результат сохранён локально и запушен на GitHub - смотри лог в репозитории.
pause
endlocal
exit /b 0
