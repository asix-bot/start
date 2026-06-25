@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [%date% %time%] Проверяю обновления скриптов из GitHub...
python update_scripts.py
if errorlevel 1 (
    echo [%date% %time%] Не удалось обновить скрипты, продолжаю с текущими версиями.
)

echo [%date% %time%] Запускаю экспорт из 1С в GitHub...
python main.py
if errorlevel 1 (
    echo [%date% %time%] main.py завершился с ошибкой.
    exit /b 1
)

echo [%date% %time%] Готово.
