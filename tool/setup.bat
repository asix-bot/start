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
echo [Шаг 4/5] Тип, расположение и суффиксы для 4 баз 1С 7.7.
echo Для каждой базы нужно указать:
echo   - тип: D = обычные DBF-файлы, S = база на SQL Server
echo   - для DBF: путь к папке, где лежат .DBF файлы базы
echo   - для SQL: имя сервера и имя базы данных
echo     подсказка - смотри в 1С: Конфигуратор -^> Администрирование -^>
echo     Администрирование информационной базы, поля Сервер баз данных
echo     и База данных. Пример сервера: SQLSRV01 или SQLSRV01\SQLEXPRESS
echo   - суффикс, который нужно добавлять к артикулу товаров этой базы
echo Пример пути DBF: C:\Bases\Base1   Пример суффикса: -B1
echo.

set "TYPE1="
set "LOC1_1="
set "LOC1_2=NONE"
set /p TYPE1=Тип базы 1 D-DBF S-SQL:
if /i "%TYPE1%"=="S" (
    set /p LOC1_1=Имя SQL-сервера для базы 1:
    set /p LOC1_2=Имя базы данных SQL для базы 1:
) else (
    set /p LOC1_1=Путь к папке с DBF-файлами базы 1:
)
set /p SUF1=Суффикс для базы 1:

set "TYPE2="
set "LOC2_1="
set "LOC2_2=NONE"
set /p TYPE2=Тип базы 2 D-DBF S-SQL:
if /i "%TYPE2%"=="S" (
    set /p LOC2_1=Имя SQL-сервера для базы 2:
    set /p LOC2_2=Имя базы данных SQL для базы 2:
) else (
    set /p LOC2_1=Путь к папке с DBF-файлами базы 2:
)
set /p SUF2=Суффикс для базы 2:

set "TYPE3="
set "LOC3_1="
set "LOC3_2=NONE"
set /p TYPE3=Тип базы 3 D-DBF S-SQL:
if /i "%TYPE3%"=="S" (
    set /p LOC3_1=Имя SQL-сервера для базы 3:
    set /p LOC3_2=Имя базы данных SQL для базы 3:
) else (
    set /p LOC3_1=Путь к папке с DBF-файлами базы 3:
)
set /p SUF3=Суффикс для базы 3:

set "TYPE4="
set "LOC4_1="
set "LOC4_2=NONE"
set /p TYPE4=Тип базы 4 D-DBF S-SQL:
if /i "%TYPE4%"=="S" (
    set /p LOC4_1=Имя SQL-сервера для базы 4:
    set /p LOC4_2=Имя базы данных SQL для базы 4:
) else (
    set /p LOC4_1=Путь к папке с DBF-файлами базы 4:
)
set /p SUF4=Суффикс для базы 4:

echo.
echo Если среди баз есть хотя бы одна SQL - укажи общий логин и пароль
echo SQL Server, через который будут читаться все SQL-базы.
set "SQLUSER=sa"
set /p SQLUSER=Логин SQL Server, Enter для sa:
set /p SQLPASS=Пароль SQL Server:

echo.
echo Записываю настройки в config.json...
python update_config.py "%TYPE1%" "%LOC1_1%" "%LOC1_2%" "%SUF1%" "%TYPE2%" "%LOC2_1%" "%LOC2_2%" "%SUF2%" "%TYPE3%" "%LOC3_1%" "%LOC3_2%" "%SUF3%" "%TYPE4%" "%LOC4_1%" "%LOC4_2%" "%SUF4%" "%SQLUSER%" "%SQLPASS%"
if errorlevel 1 (
    echo.
    echo ОШИБКА при обновлении config.json. Проверь сообщение выше.
    pause
    exit /b 1
)
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 5/5] Запуск разведчика структуры баз explore.py...
echo Это покажет, какие таблицы и поля есть в каждой базе DBF и SQL,
echo и сохранит report.txt локально, а также запушит его в GitHub если в
echo config.json уже указан токен.
echo.
python explore.py
if errorlevel 1 (
    echo.
    echo Разведчик завершился с ошибкой. Прочитай сообщение выше.
    pause
    exit /b 1
)
echo.
echo Готово. Файл report.txt создан рядом с этим bat-файлом
echo и если настроено запушен в репозиторий на GitHub.
pause

:: ------------------------------------------------------------------
echo.
echo ============================================================
echo  Готово! report.txt опубликован в репозитории GitHub.
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
