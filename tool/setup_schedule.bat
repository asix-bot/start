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
echo  Настройка автозапуска run_export.bat.
echo  Запуск каждый час и при старте Windows через Task Scheduler.
echo  Каждый запуск сам подтягивает свежие версии скриптов из GitHub
echo  перед экспортом.
echo ============================================================
echo.
set "SCHEDULE_YN="
set /p SCHEDULE_YN=Настроить автозапуск? (Y/N):
if /i not "%SCHEDULE_YN%"=="Y" goto SKIP_SCHEDULE

set "SCRIPT_DIR=%~dp0"
set "TASK_NAME_HOURLY=1C Export to GitHub (hourly)"
set "TASK_NAME_STARTUP=1C Export to GitHub (on startup)"

rem /ru SYSTEM - чтобы задачи срабатывали ДАЖЕ если никто не залогинен в
rem Windows (без /ru SYSTEM Task Scheduler привязывает задачу к интерактивному
rem входу текущего пользователя - после перезагрузки без логина она просто
rem не запускается, хотя в списке задач выглядит "включённой").
rem /rl HIGHEST - права администратора (нужно для устойчивой работы под SYSTEM).
schtasks /delete /tn "%TASK_NAME_HOURLY%" /f >nul 2>&1
schtasks /delete /tn "%TASK_NAME_STARTUP%" /f >nul 2>&1

rem /st 00:55:00 - якорь времени: задача стартует в чч:55 и повторяется
rem каждый час от этой точки (09:55, 10:55, 11:55 и так далее).
schtasks /create /tn "%TASK_NAME_HOURLY%" /tr "\"%SCRIPT_DIR%run_export.bat\" /silent" /sc hourly /st 00:55:00 /ru SYSTEM /rl HIGHEST /f
set "HOURLY_RC=%ERRORLEVEL%"
schtasks /create /tn "%TASK_NAME_STARTUP%" /tr "\"%SCRIPT_DIR%run_export.bat\" /silent" /sc onstart /delay 0001:00 /ru SYSTEM /rl HIGHEST /f
set "STARTUP_RC=%ERRORLEVEL%"

if "%HOURLY_RC%"=="0" if "%STARTUP_RC%"=="0" (
    echo.
    echo Готово. Созданы задачи в Task Scheduler:
    echo   - "%TASK_NAME_HOURLY%" - запуск каждый час
    echo   - "%TASK_NAME_STARTUP%" - запуск при старте Windows
    echo Посмотреть/изменить их можно через "Планировщик заданий" Windows.
    echo Удалить: schtasks /delete /tn "%TASK_NAME_HOURLY%" /f ^&^& schtasks /delete /tn "%TASK_NAME_STARTUP%" /f
) else (
    echo.
    echo ОШИБКА при создании одной или обеих задач. Попробуй запустить
    echo этот bat от имени администратора правой кнопкой -^>
    echo "Запуск от имени администратора" - задача с /ru SYSTEM требует прав.
)

:SKIP_SCHEDULE
echo.
pause
endlocal
exit /b 0
