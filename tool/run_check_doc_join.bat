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
    echo Использование: check_doc_join.py индекс_базы-1-4 IDDOC1 IDDOC2 и так далее
    echo Пример: check_doc_join.py 3 2LWI 34AE
    pause
    exit /b 1
)

%PYTHON% check_doc_join.py %*
echo.
echo Результат сохранён локально и запушен на GitHub - смотри лог в репозитории.
pause
endlocal
exit /b 0
