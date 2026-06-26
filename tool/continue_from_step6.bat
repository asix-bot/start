@echo off
chcp 866 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

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
echo  1C 7.7 -^> CSV -^> GitHub.  Продолжение с шага 6 сопоставление полей.
echo  Используй этот файл, если уже прогонял setup.bat создан report.txt,
echo  config.json с путями/суффиксами, и сопоставление таблиц/полей
echo  уже готово и лежит в репозитории как bases_mapping.json.
echo ============================================================
echo.
pause

if not exist config.json (
    echo.
    echo ОШИБКА: config.json не найден в этой папке.
    echo Сначала запусти setup.bat хотя бы до шага 4, чтобы создать config.json
    echo с путями и суффиксами баз.
    pause
    exit /b 1
)

echo.
echo [Шаг 6/7] Скачиваю bases_mapping.json из репозитория GitHub
echo и подмешиваю сопоставление таблиц/полей в config.json
echo пути и суффиксы баз, а также токен ? не трогаются.
echo.
%PYTHON% merge_field_mapping.py
if errorlevel 1 (
    echo.
    echo Не удалось подтянуть сопоставление полей. Прочитай сообщение выше:
    echo либо bases_mapping.json ещё не запушен в репозиторий, либо ошибка
    echo доступа. Можно попробовать снова после того, как файл появится
    echo в репозитории.
    pause
    exit /b 1
)

echo.
echo Сопоставление подтянуто. Нажми Enter, чтобы запустить основной экспорт.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 7/7] Запуск основного экспорта run_export.bat...
echo Сначала подтянутся свежие версии скриптов из репозитория папка tool/,
echo затем прочитаются все 4 базы по config.json, соберётся один CSV
echo и запушится в GitHub.
echo.
call run_export.bat
if errorlevel 1 (
    echo.
    echo Экспорт завершился с ошибкой. Прочитай сообщение выше,
    echo поправь config.json вероятно, неверные имена таблиц/полей
    echo и запусти этот bat заново.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Готово! CSV опубликован в репозитории GitHub.
echo  Чтобы повторить экспорт позже, можно просто запускать: run_export.bat
echo ============================================================
pause

:: ------------------------------------------------------------------
echo.
echo [Доп. шаг] Автозапуск.
echo Поставить run_export.bat на автозапуск при старте Windows
echo и дополнительно по расписанию каждый час? Каждый запуск сам
echo подтягивает свежие версии скриптов из GitHub перед экспортом.
echo.
set "SCHEDULE_YN="
set /p SCHEDULE_YN=Настроить автозапуск? (Y/N):
if /i not "%SCHEDULE_YN%"=="Y" goto SKIP_SCHEDULE

set "SCRIPT_DIR=%~dp0"
set "TASK_NAME_HOURLY=1C Export to GitHub (hourly)"
set "TASK_NAME_STARTUP=1C Export to GitHub (on startup)"

schtasks /create /tn "%TASK_NAME_HOURLY%" /tr "\"%SCRIPT_DIR%run_export.bat\"" /sc hourly /f
set "HOURLY_RC=%ERRORLEVEL%"
schtasks /create /tn "%TASK_NAME_STARTUP%" /tr "\"%SCRIPT_DIR%run_export.bat\"" /sc onstart /delay 0001:00 /ru SYSTEM /f
set "STARTUP_RC=%ERRORLEVEL%"

if "%HOURLY_RC%"=="0" if "%STARTUP_RC%"=="0" (
    echo.
    echo Готово. Созданы задачи в Task Scheduler:
    echo   - "%TASK_NAME_HOURLY%" ? запуск каждый час
    echo   - "%TASK_NAME_STARTUP%" ? запуск при старте Windows
    echo Посмотреть/изменить их можно через "Планировщик заданий" Windows.
    echo Удалить: schtasks /delete /tn "%TASK_NAME_HOURLY%" /f ^&^& schtasks /delete /tn "%TASK_NAME_STARTUP%" /f
) else (
    echo.
    echo ОШИБКА при создании одной или обеих задач. Попробуй запустить
    echo этот bat от имени администратора правой кнопкой -^>
    echo "Запуск от имени администратора" ? задача с /ru SYSTEM требует прав.
)

:SKIP_SCHEDULE
echo.
pause
endlocal
exit /b 0
