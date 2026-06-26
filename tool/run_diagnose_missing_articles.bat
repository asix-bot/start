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
    echo Использование: diagnose_missing_articles.py арт1 [арт2 ...]
    echo Пример: diagnose_missing_articles.py 9714ки 7397ки 5687з
    pause
    exit /b 1
)

%PYTHON% diagnose_missing_articles.py %*
echo.
echo Результат сохранён локально и - если настроен токен GitHub - запушен
echo в репозиторий, можно скачать без скриншотов терминала.
pause
endlocal
exit /b 0
