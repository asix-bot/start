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
echo  Обновление всех файлов проекта из репозитория GitHub.
echo  Включая все bat-файлы - setup.bat, run_export.bat и т.д.
echo ============================================================
echo.

if not exist config.json (
    echo ОШИБКА: config.json не найден в этой папке.
    echo Этот файл нужен, чтобы знать репозиторий и токен GitHub.
    echo Если config.json ещё нет на этой машине - сначала нужно
    echo получить его другим способом, этот bat не создаёт его с нуля.
    pause
    exit /b 1
)

%PYTHON% update_scripts.py
if errorlevel 1 (
    echo.
    echo Обновление завершилось с ошибкой. Прочитай сообщение выше.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Готово. Все файлы обновлены до последней версии из репозитория.
echo  Теперь можно запускать setup.bat или continue_from_step6.bat.
echo ============================================================
pause
endlocal
exit /b 0
