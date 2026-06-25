@echo off
chcp 866 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo  1C 7.7 -^> CSV -^> GitHub.  Пошаговый запуск.
echo  На каждом шаге читай текст и нажимай Enter, чтобы продолжить.
echo ============================================================
echo.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 1/6] Проверка Python...
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo ОШИБКА: Python не найден в PATH.
    echo Скачай и установи с https://www.python.org/downloads/
    echo (на Windows 7 / Server 2008 R2 нужна версия 3.8.x ? новее не ставится).
    echo При установке поставь галочку "Add Python to PATH", затем запусти
    echo этот файл заново.
    echo.
    pause
    exit /b 1
)
python --version
echo Python найден.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 2/6] Проверка Git...
where git >nul 2>nul
if errorlevel 1 (
    echo.
    echo ОШИБКА: Git не найден в PATH.
    echo Скачай и установи с https://git-scm.com/download/win
    echo (на Windows 7 / Server 2008 R2 нужна версия не новее 2.46.0 ?
    echo начиная с 2.47 инсталлятор сам блокирует установку на этих ОС).
    echo затем запусти этот файл заново.
    echo.
    pause
    exit /b 1
)
git --version
echo Git найден.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 3/6] Проверка TLS 1.2 и доступа к GitHub...
echo GitHub требует TLS 1.2 для HTTPS. На старых ОС (Windows 7 /
echo Server 2008 R2) он часто не включён по умолчанию ? без него
echo git clone/push к GitHub будет падать с ошибкой соединения.
echo.
git ls-remote https://github.com/asix-bot/start.git >nul 2>nul
if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось подключиться к GitHub по HTTPS.
    echo Скорее всего, причина ? отсутствие поддержки TLS 1.2 в системе.
    echo Что сделать:
    echo   1. Установить обновление KB3140245 с Microsoft Update Catalog
    echo      (оно включает TLS 1.2 по умолчанию для системных компонентов).
    echo   2. Перезагрузить сервер.
    echo   3. Запустить этот файл заново.
    echo Если после этого ошибка останется ? проверь подключение к интернету
    echo и доступность github.com (фаервол/прокси).
    echo.
    pause
    exit /b 1
)
echo Соединение с GitHub по HTTPS работает, TLS 1.2 в порядке.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 4/6] Установка зависимости dbfread...
pip install dbfread
if errorlevel 1 (
    echo.
    echo ОШИБКА при установке dbfread. Проверь подключение к интернету и повтори.
    pause
    exit /b 1
)
echo Готово.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 5/6] Пути и суффиксы для 4 баз 1С 7.7.
echo Для каждой базы укажи путь к папке с DBF-файлами и суффикс,
echo который нужно добавлять к артикулу товаров этой базы.
echo Пример пути: C:\Bases\Base1   Пример суффикса: -B1
echo.
set "BASE1="
set "BASE2="
set "BASE3="
set "BASE4="
set "SUF1="
set "SUF2="
set "SUF3="
set "SUF4="
set /p BASE1=Путь к базе 1:
set /p SUF1=Суффикс для базы 1:
set /p BASE2=Путь к базе 2:
set /p SUF2=Суффикс для базы 2:
set /p BASE3=Путь к базе 3:
set /p SUF3=Суффикс для базы 3:
set /p BASE4=Путь к базе 4:
set /p SUF4=Суффикс для базы 4:

echo.
echo Проверка путей...
set "BASES_OK=1"
if not exist "%BASE1%" (echo   НЕ НАЙДЕН: %BASE1% & set "BASES_OK=0")
if not exist "%BASE2%" (echo   НЕ НАЙДЕН: %BASE2% & set "BASES_OK=0")
if not exist "%BASE3%" (echo   НЕ НАЙДЕН: %BASE3% & set "BASES_OK=0")
if not exist "%BASE4%" (echo   НЕ НАЙДЕН: %BASE4% & set "BASES_OK=0")

if "%BASES_OK%"=="0" (
    echo.
    echo Один или несколько путей не найдены. Проверь и запусти файл заново.
    pause
    exit /b 1
)
echo Все 4 пути найдены.

echo.
echo Записываю пути и суффиксы в config.json...
python update_config.py "%BASE1%" "%SUF1%" "%BASE2%" "%SUF2%" "%BASE3%" "%SUF3%" "%BASE4%" "%SUF4%"
if errorlevel 1 (
    echo.
    echo ОШИБКА при обновлении config.json. Проверь сообщение выше.
    pause
    exit /b 1
)
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 6/6] Запуск разведчика структуры баз (explore_dbf.py)...
echo Это покажет, какие таблицы и поля есть в каждой базе, и сохранит
echo report.txt локально, а также запушит его в GitHub (если в
echo config.json уже указан токен).
echo.
python explore_dbf.py "%BASE1%" "%BASE2%" "%BASE3%" "%BASE4%"
if errorlevel 1 (
    echo.
    echo Разведчик завершился с ошибкой. Прочитай сообщение выше.
    pause
    exit /b 1
)
echo.
echo Готово. Файл report.txt создан рядом с этим bat-файлом
echo и (если настроено) запушен в репозиторий на GitHub.
pause

:: ------------------------------------------------------------------
echo.
echo ============================================================
echo  Готово! report.txt опубликован в репозитории GitHub.
echo.
echo  Дальше: сообщи в чат, что report.txt готов в репозитории ?
echo  по нему подготовят bases_mapping.json с сопоставлением таблиц/полей
echo  и запушат его в тот же репозиторий.
echo.
echo  Когда bases_mapping.json появится в репозитории ? запусти файл
echo  continue_from_step6.bat в этой же папке. Он подтянет сопоставление,
echo  запустит экспорт и предложит настроить автозапуск по расписанию.
echo ============================================================
pause
endlocal
exit /b 0
