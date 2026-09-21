@echo off
cd /d "%~dp0"

:: Чистим системный Temp
del /q /f "%TEMP%\*" 2>nul
for /d %%i in ("%TEMP%\*") do rd /s /q "%%i" 2>nul

del /q /f "%TMP%\*" 2>nul
for /d %%i in ("%TMP%\*") do rd /s /q "%%i" 2>nul

:: Чистим Windows\Temp
del /q /f "C:\Windows\Temp\*" 2>nul
for /d %%i in ("C:\Windows\Temp\*") do rd /s /q "%%i" 2>nul

echo [%date% %time%] Temp cleaned.
