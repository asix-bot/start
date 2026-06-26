@echo off
chcp 866 >nul
cd /d "%~dp0"

set "PYTHON=C:\Python34\python.exe"

if not exist "%PYTHON%" (
    echo.
    echo ОШИБКА: не найден Python по пути %PYTHON%
    echo Поправь путь в строке set "PYTHON=..." в начале этого файла.
    echo.
    pause
    exit /b 1
)

echo [%date% %time%] Проверяю обновления скриптов из GitHub...
%PYTHON% update_scripts.py
if errorlevel 1 (
    echo [%date% %time%] Не удалось обновить скрипты, продолжаю с текущими версиями.
)

echo [%date% %time%] Запускаю экспорт из 1С в GitHub...
%PYTHON% main.py
if errorlevel 1 (
    echo [%date% %time%] main.py завершился с ошибкой.
    exit /b 1
)

echo [%date% %time%] Готово.

if /i not "%~1"=="/silent" (
    pause
)
