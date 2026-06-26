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
echo [Шаг 1/5] Проверка Git...
where git >nul 2>nul
if errorlevel 1 (
    echo.
    echo ОШИБКА: Git не найден в PATH.
    echo Скачай и установи с https://git-scm.com/download/win
    echo на Windows 7 / Server 2008 R2 нужна версия не новее 2.46.0 -
    echo начиная с 2.47 инсталлятор сам блокирует установку на этих ОС.
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
echo [Шаг 2/5] Проверка TLS 1.2 и доступа к GitHub...
echo GitHub требует TLS 1.2 для HTTPS. На старых ОС Windows 7 /
echo Server 2008 R2 он часто не включён по умолчанию - без него
echo git clone/push к GitHub будет падать с ошибкой соединения.
echo.
git ls-remote https://github.com/asix-bot/start.git >nul 2>nul
if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось подключиться к GitHub по HTTPS.
    echo Скорее всего, причина - отсутствие поддержки TLS 1.2 в системе.
    echo Что сделать:
    echo   1. Установить обновление KB3140245 с Microsoft Update Catalog
    echo      оно включает TLS 1.2 по умолчанию для системных компонентов.
    echo   2. Перезагрузить сервер.
    echo   3. Запустить этот файл заново.
    echo Если после этого ошибка останется - проверь подключение к интернету
    echo и доступность github.com - фаервол/прокси.
    echo.
    pause
    exit /b 1
)
echo Соединение с GitHub по HTTPS работает, TLS 1.2 в порядке.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 3/5] Проверка dbfread...
echo dbfread уже идет вместе с проектом папка dbfread/, отдельно ставить
echo не нужно. Если вдруг папки нет - пробуем поставить через pip как запасной
echo вариант может не сработать на очень старых ОС без TLS 1.2 в pip.
if not exist "%~dp0dbfread\__init__.py" (
    echo Папка dbfread/ не найдена, пробую pip install dbfread...
    pip install dbfread
    if errorlevel 1 (
        echo.
        echo ОШИБКА: не удалось ни найти папку dbfread/, ни поставить через pip.
        echo Скопируй папку dbfread/ из репозитория - tool/dbfread - рядом с этим
        echo bat-файлом и запусти заново.
        pause
        exit /b 1
    )
)
echo Готово.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 4/5] Базы 1С 7.7 - по одной, с проверкой каждой сразу.
echo Для каждой базы нужно указать:
echo   - тип: D = обычные DBF-файлы, S = база на SQL Server
echo   - для DBF: путь к папке, где лежат .DBF файлы базы
echo   - для SQL: имя сервера и имя базы данных
echo     подсказка - смотри в 1С: Конфигуратор -^> Администрирование -^>
echo     Администрирование информационной базы, поля Сервер баз данных
echo     и База данных. Пример сервера: SQLSRV01 или SQLSRV01\SQLEXPRESS
echo После ввода данных скрипт сразу проверит, что база реально читается -
echo если нет, спросит данные этой же базы заново, остальные базы не тронет.
echo.

set "SQLUSER=sa"
set /p SQLUSER=Логин SQL Server общий для всех SQL-баз, Enter для sa:
set /p SQLPASS=Пароль SQL Server:

:BASE1_INPUT
echo.
echo --- База 1 из 4: Шишина ---
set "TYPE1="
set "LOC1_1="
set "LOC1_2=NONE"
set /p TYPE1=Тип базы Шишина D-DBF S-SQL:
if /i "%TYPE1%"=="S" (
    set /p LOC1_1=Имя SQL-сервера для базы Шишина:
    set /p LOC1_2=Имя базы данных SQL для базы Шишина:
) else (
    set /p LOC1_1=Путь к папке с DBF-файлами базы Шишина:
)
python update_config.py 1 "%TYPE1%" "%LOC1_1%" "%LOC1_2%" "%SQLUSER%" "%SQLPASS%"
if errorlevel 1 (
    echo ОШИБКА при записи config.json. Введи данные базы Шишина заново.
    goto BASE1_INPUT
)
echo Проверяю базу Шишина...
python check_base.py 1
if errorlevel 1 (
    echo.
    echo Проверка базы Шишина не прошла. Прочитай сообщение выше,
    echo поправь данные и попробуй снова.
    pause
    goto BASE1_INPUT
)
echo База Шишина проверена успешно.
pause

:BASE2_INPUT
echo.
echo --- База 2 из 4: Киселев ---
set "TYPE2="
set "LOC2_1="
set "LOC2_2=NONE"
set /p TYPE2=Тип базы Киселев D-DBF S-SQL:
if /i "%TYPE2%"=="S" (
    set /p LOC2_1=Имя SQL-сервера для базы Киселев:
    set /p LOC2_2=Имя базы данных SQL для базы Киселев:
) else (
    set /p LOC2_1=Путь к папке с DBF-файлами базы Киселев:
)
python update_config.py 2 "%TYPE2%" "%LOC2_1%" "%LOC2_2%" "%SQLUSER%" "%SQLPASS%"
if errorlevel 1 (
    echo ОШИБКА при записи config.json. Введи данные базы Киселев заново.
    goto BASE2_INPUT
)
echo Проверяю базу Киселев...
python check_base.py 2
if errorlevel 1 (
    echo.
    echo Проверка базы Киселев не прошла. Прочитай сообщение выше,
    echo поправь данные и попробуй снова.
    pause
    goto BASE2_INPUT
)
echo База Киселев проверена успешно.
pause

:BASE3_INPUT
echo.
echo --- База 3 из 4: Захарина ---
set "TYPE3="
set "LOC3_1="
set "LOC3_2=NONE"
set /p TYPE3=Тип базы Захарина D-DBF S-SQL:
if /i "%TYPE3%"=="S" (
    set /p LOC3_1=Имя SQL-сервера для базы Захарина:
    set /p LOC3_2=Имя базы данных SQL для базы Захарина:
) else (
    set /p LOC3_1=Путь к папке с DBF-файлами базы Захарина:
)
python update_config.py 3 "%TYPE3%" "%LOC3_1%" "%LOC3_2%" "%SQLUSER%" "%SQLPASS%"
if errorlevel 1 (
    echo ОШИБКА при записи config.json. Введи данные базы Захарина заново.
    goto BASE3_INPUT
)
echo Проверяю базу Захарина...
python check_base.py 3
if errorlevel 1 (
    echo.
    echo Проверка базы Захарина не прошла. Прочитай сообщение выше,
    echo поправь данные и попробуй снова.
    pause
    goto BASE3_INPUT
)
echo База Захарина проверена успешно.
pause

:BASE4_INPUT
echo.
echo --- База 4 из 4: Кукушкина ---
set "TYPE4="
set "LOC4_1="
set "LOC4_2=NONE"
set /p TYPE4=Тип базы Кукушкина D-DBF S-SQL:
if /i "%TYPE4%"=="S" (
    set /p LOC4_1=Имя SQL-сервера для базы Кукушкина:
    set /p LOC4_2=Имя базы данных SQL для базы Кукушкина:
) else (
    set /p LOC4_1=Путь к папке с DBF-файлами базы Кукушкина:
)
python update_config.py 4 "%TYPE4%" "%LOC4_1%" "%LOC4_2%" "%SQLUSER%" "%SQLPASS%"
if errorlevel 1 (
    echo ОШИБКА при записи config.json. Введи данные базы Кукушкина заново.
    goto BASE4_INPUT
)
echo Проверяю базу Кукушкина...
python check_base.py 4
if errorlevel 1 (
    echo.
    echo Проверка базы Кукушкина не прошла. Прочитай сообщение выше,
    echo поправь данные и попробуй снова.
    pause
    goto BASE4_INPUT
)
echo База Кукушкина проверена успешно.
pause

:: ------------------------------------------------------------------
echo.
echo ============================================================
echo  Готово! Все 4 базы проверены, report.txt опубликован в репозитории.
echo.
echo  Дальше: сообщи в чат, что report.txt готов в репозитории -
echo  по нему подготовят bases_mapping.json с сопоставлением таблиц/полей
echo  и запушат его в тот же репозиторий.
echo.
echo  Когда bases_mapping.json появится в репозитории - запусти файл
echo  continue_from_step6.bat в этой же папке. Он подтянет сопоставление,
echo  запустит экспорт и предложит настроить автозапуск по расписанию.
echo ============================================================
pause
endlocal
exit /b 0
