@echo off
chcp 866 >nul
cd /d "%~dp0"

set "PYTHON=C:\Python34\python.exe"

if not exist "%PYTHON%" (
    echo.
    echo Ошибка: не найден Python по пути %PYTHON%
    echo Поправь путь в строке set "PYTHON=..." в начале этого файла.
    echo.
    pause
    exit /b 1
)

echo Этот запуск принудительно пересчитает цену/себестоимость прямо сейчас,
echo не дожидаясь вечернего окна 19:00-23:59 - для разовой проверки.
echo.
echo [%date% %time%] Проверяю обновления скриптов из GitHub...
%PYTHON% update_scripts.py
if errorlevel 1 (
    echo [%date% %time%] Не удалось обновить скрипты, продолжаю с текущими файлами.
)

echo [%date% %time%] Запускаю экспорт из 1С в GitHub (с принудительным пересчётом цены)...
%PYTHON% main.py --force-price-recalc
if errorlevel 1 (
    echo [%date% %time%] main.py завершился с ошибкой.
    pause
    exit /b 1
)

echo [%date% %time%] Готово.
pause
