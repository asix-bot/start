@echo off
chcp 866 >nul
setlocal

echo ============================================================
echo  Включение TLS 1.2 в реестре (после установки KB3140245).
echo  Нужны права администратора.
echo ============================================================
echo.

:: Проверка прав администратора (классический трюк, работает и на
:: Server 2008 R2): пробуем открыть на запись системный файл реестра.
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if not "%errorlevel%"=="0" (
    echo ОШИБКА: нужны права администратора.
    echo Запусти этот файл правой кнопкой -^> "Запуск от имени администратора".
    pause
    exit /b 1
)

echo Правлю реестр...
echo.

:: 1. WinHTTP - включаем TLS 1.2 по умолчанию (это и есть основная
::    цель KB3140245 - до установки этого обновления данных ключей
::    в системе попросту нет).
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings\WinHttp" /v DefaultSecureProtocols /t REG_DWORD /d 0x00000800 /f
reg add "HKLM\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Internet Settings\WinHttp" /v DefaultSecureProtocols /t REG_DWORD /d 0x00000800 /f

:: 2. .NET Framework - "сильная" криптография, чтобы приложения на
::    .NET (например, PowerShell с Net.WebClient) тоже использовали
::    TLS 1.2, а не старый протокол по умолчанию.
reg add "HKLM\SOFTWARE\Microsoft\.NETFramework\v4.0.30319" /v SchUseStrongCrypto /t REG_DWORD /d 1 /f
reg add "HKLM\SOFTWARE\Wow6432Node\Microsoft\.NETFramework\v4.0.30319" /v SchUseStrongCrypto /t REG_DWORD /d 1 /f

:: 3. SCHANNEL - явно включаем протокол TLS 1.2 на уровне ОС. Это
::    важно для свежих версий Git for Windows, которые по умолчанию
::    используют системный (Windows-native) TLS вместо встроенного
::    OpenSSL.
reg add "HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.2\Client" /v Enabled /t REG_DWORD /d 1 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.2\Client" /v DisabledByDefault /t REG_DWORD /d 0 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.2\Server" /v Enabled /t REG_DWORD /d 1 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL\Protocols\TLS 1.2\Server" /v DisabledByDefault /t REG_DWORD /d 0 /f

echo.
echo ============================================================
echo  Готово. Реестр изменен.
echo  ВАЖНО: нужно перезагрузить сервер, чтобы изменения вступили
echo  в силу, иначе TLS 1.2 не заработает.
echo.
echo  После перезагрузки запусти setup.bat заново - шаг проверки
echo  TLS 1.2 должен пройти успешно.
echo ============================================================
echo.
set "REBOOT_YN="
set /p REBOOT_YN=Перезагрузить сервер сейчас? (Y/N):
if /i "%REBOOT_YN%"=="Y" (
    shutdown /r /t 10 /c "Перезагрузка для применения настроек TLS 1.2"
    echo Перезагрузка через 10 секунд. Чтобы отменить: shutdown /a
) else (
    echo Не забудь перезагрузить сервер вручную перед следующим запуском setup.bat.
)
pause
endlocal
exit /b 0
