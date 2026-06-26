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

echo ============================================================
echo  Сброс и повторная проверка только базы Шишина.
echo  Путь и тип базы не трогаются - они уже настроены в config.json.
echo ============================================================
echo.

%PYTHON% reset_base.py 1
if errorlevel 1 (
    echo.
    echo ОШИБКА при сбросе флага verified. Прочитай сообщение выше.
    pause
    exit /b 1
)

%PYTHON% check_base.py 1
if errorlevel 1 (
    echo.
    echo Проверка базы Шишина завершилась с ошибкой. Прочитай сообщение выше -
    echo полный текст также в файле last_check_error.txt
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Готово. report.txt для базы Шишина обновлён и запушен в GitHub.
echo ============================================================
pause
endlocal
exit /b 0
