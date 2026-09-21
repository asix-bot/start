@echo off
cd /d "%~dp0"

set "TASK_NAME=1C Cleanup Temp (daily)"
set "SCRIPT_DIR=%~dp0"

schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_DIR%cleanup_temp.bat\"" /sc daily /st 03:00:00 /ru SYSTEM /rl HIGHEST /f

if "%ERRORLEVEL%"=="0" (
    echo OK: task "%TASK_NAME%" scheduled daily at 03:00.
) else (
    echo ERROR: failed to create task. Run this bat as Administrator.
)
pause
