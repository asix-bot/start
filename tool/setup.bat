@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo  1C 7.7 -^> CSV -^> GitHub.  Пошаговый запуск.
echo  На каждом шаге читай текст и нажимай Enter, чтобы продолжить.
echo ============================================================
echo.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 1/5] Проверка Python...
where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Пытаюсь установить автоматически...
    call :INSTALL_PYTHON
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo Не удалось установить Python автоматически.
        echo Скачай и установи вручную с https://www.python.org/downloads/
        echo При установке поставь галочку "Add Python to PATH", затем запусти
        echo этот файл заново.
        echo.
        pause
        exit /b 1
    )
)
python --version
echo Python найден.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 2/5] Проверка Git...
where git >nul 2>nul
if errorlevel 1 (
    echo Git не найден. Пытаюсь установить автоматически...
    call :INSTALL_GIT
    where git >nul 2>nul
    if errorlevel 1 (
        echo.
        echo Не удалось установить Git автоматически.
        echo Скачай и установи вручную с https://git-scm.com/download/win
        echo затем запусти этот файл заново.
        echo.
        pause
        exit /b 1
    )
)
git --version
echo Git найден.
pause

:: ------------------------------------------------------------------
echo.
echo [Шаг 3/5] Установка зависимости dbfread...
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
echo [Шаг 4/5] Пути и суффиксы для 4 баз 1С 7.7.
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
echo [Шаг 5/5] Запуск разведчика структуры баз (explore_dbf.py)...
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
echo  Дальше: сообщи в чат, что report.txt готов в репозитории —
echo  по нему подготовят bases_mapping.json с сопоставлением таблиц/полей
echo  и запушат его в тот же репозиторий.
echo.
echo  Когда bases_mapping.json появится в репозитории — запусти файл
echo  continue_from_step6.bat в этой же папке. Он подтянет сопоставление,
echo  запустит экспорт и предложит настроить автозапуск по расписанию.
echo ============================================================
pause
endlocal
exit /b 0

:: ====================================================================
:: Подпрограммы автоустановки. Используют winget, если он есть
:: (стандартно есть на Windows 10/11 с обновлениями), иначе скачивают
:: официальный установщик с python.org / git-scm.com и ставят его тихо.
::
:: На старых ОС (Windows 7 / Server 2008 R2, ядро NT 6.1 и старше) ставят
:: последние версии, которые там ещё официально работают:
::   - Python 3.8.10 (Python 3.9+ требует Windows 8.1 и новее)
::   - Git for Windows 2.46.0 (начиная с 2.47 инсталлятор сам блокирует
::     установку на Windows 7/8)
:: Битность (32/64) определяется автоматически по архитектуре системы.
:: ====================================================================

:DETECT_ENV
:: Определяем версию ОС (major.minor ядра NT) через wmic.
set "OS_MAJOR=10"
set "OS_MINOR=0"
for /f "tokens=2 delims==" %%v in ('wmic os get Version /value 2^>nul ^| findstr /i "Version"') do set "WIN_VERSION_RAW=%%v"
if defined WIN_VERSION_RAW (
    for /f "tokens=1,2 delims=." %%a in ("%WIN_VERSION_RAW%") do (
        set "OS_MAJOR=%%a"
        set "OS_MINOR=%%b"
    )
)
set "IS_OLD_OS=0"
if %OS_MAJOR% LSS 6 set "IS_OLD_OS=1"
if %OS_MAJOR%==6 if %OS_MINOR% LEQ 1 set "IS_OLD_OS=1"

:: Определяем разрядность ОС (а не текущего процесса/cmd).
set "OS_BITS=64"
if not defined PROCESSOR_ARCHITEW6432 if "%PROCESSOR_ARCHITECTURE%"=="x86" set "OS_BITS=32"

if "%IS_OLD_OS%"=="1" (
    echo Обнаружена старая Windows (ядро NT %OS_MAJOR%.%OS_MINOR%, %OS_BITS%-bit) —
    echo использую последние версии Python/Git, которые её ещё поддерживают.
)
exit /b 0

:DOWNLOAD_FILE
:: %1 = URL, %2 = куда сохранить. Сначала пробуем curl (есть на Windows 10+),
:: иначе используем PowerShell WebClient с принудительным TLS 1.2 (нужен
:: для скачивания с github.com/python.org на старых ОС без хотфикса TLS 1.2).
where curl >nul 2>nul
if not errorlevel 1 (
    curl -L -o "%~2" "%~1"
    exit /b 0
)
powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%~1', '%~2')"
exit /b 0

:INSTALL_PYTHON
call :DETECT_ENV
where winget >nul 2>nul
if not errorlevel 1 if "%IS_OLD_OS%"=="0" (
    echo Устанавливаю Python через winget...
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    goto REFRESH_PATH_PYTHON
)

if "%IS_OLD_OS%"=="1" (
    if "%OS_BITS%"=="32" (
        set "PY_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10.exe"
    ) else (
        set "PY_URL=https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe"
    )
) else (
    if "%OS_BITS%"=="32" (
        set "PY_URL=https://www.python.org/ftp/python/3.12.4/python-3.12.4.exe"
    ) else (
        set "PY_URL=https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
    )
)

echo Скачиваю установщик Python (%PY_URL%)...
set "PY_INSTALLER=%TEMP%\python-installer.exe"
call :DOWNLOAD_FILE "%PY_URL%" "%PY_INSTALLER%"
if not exist "%PY_INSTALLER%" (
    echo Не удалось скачать установщик Python.
    exit /b 1
)
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0
del "%PY_INSTALLER%" >nul 2>nul

:REFRESH_PATH_PYTHON
:: Текущая сессия cmd не видит обновлённый PATH после установки,
:: поэтому добавляем типичный путь установки вручную.
for /f "delims=" %%P in ('dir /b /s "%LocalAppData%\Programs\Python\Python3*\python.exe" 2^>nul') do (
    for %%D in ("%%P") do set "PATH=%PATH%;%%~dpD;%%~dpDScripts"
)
exit /b 0

:INSTALL_GIT
call :DETECT_ENV
where winget >nul 2>nul
if not errorlevel 1 if "%IS_OLD_OS%"=="0" (
    echo Устанавливаю Git через winget...
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
    goto REFRESH_PATH_GIT
)

if "%IS_OLD_OS%"=="1" (
    if "%OS_BITS%"=="32" (
        set "GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-32-bit.exe"
    ) else (
        set "GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-64-bit.exe"
    )
) else (
    if "%OS_BITS%"=="32" (
        set "GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-32-bit.exe"
    ) else (
        set "GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe"
    )
)

echo Скачиваю установщик Git (%GIT_URL%)...
set "GIT_INSTALLER=%TEMP%\git-installer.exe"
call :DOWNLOAD_FILE "%GIT_URL%" "%GIT_INSTALLER%"
if not exist "%GIT_INSTALLER%" (
    echo Не удалось скачать установщик Git.
    exit /b 1
)
"%GIT_INSTALLER%" /VERYSILENT /NORESTART /NOCANCEL /SP- /SUPPRESSMSGBOXES
del "%GIT_INSTALLER%" >nul 2>nul

:REFRESH_PATH_GIT
if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
if exist "%LocalAppData%\Programs\Git\cmd\git.exe" set "PATH=%PATH%;%LocalAppData%\Programs\Git\cmd"
if "%IS_OLD_OS%"=="1" (
    echo.
    echo ВАЖНО: на старых ОС GitHub требует TLS 1.2, который часто не включён
    echo по умолчанию. Если дальше будут ошибки соединения при git clone/push —
    echo нужно поставить обновление KB3140245 и включить TLS 1.2 в реестре,
    echo затем перезагрузить сервер.
)
exit /b 0
