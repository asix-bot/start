@echo off
chcp 866 >nul
cd /d "%~dp0"

set "PYTHON=C:\Python34\python.exe"

if not exist "%PYTHON%" (
    echo.
    echo �訡��: �� ������ Python �� ��� %PYTHON%
    echo ���ࠢ� ���� � ��ப� set "PYTHON=..." � ��砫� �⮣� 䠩��.
    echo.
    pause
    exit /b 1
)

echo ��� ����� �ਭ㤨⥫쭮 �����⠥� 業�/ᥡ��⮨����� ��אַ ᥩ��,
echo �� ��������� ���୥�� ���� 19:00-23:59 - ��� ࠧ���� �஢�ન.
echo.
echo [%date% %time%] �஢���� ���������� �ਯ⮢ �� GitHub...
%PYTHON% update_scripts.py
if errorlevel 1 (
    echo [%date% %time%] �� 㤠���� �������� �ਯ��, �த����� � ⥪�騬� 䠩����.
)

echo [%date% %time%] ����⠥� ��-�������-⨯ price_cache.json...
if exist price_cache.json del price_cache.json

echo [%date% %time%] ����᪠� ��ᯮ�� �� 1� � GitHub (� �ਭ㤨⥫�� ������⮬ 業�)...
%PYTHON% main.py --force-price-recalc
if errorlevel 1 (
    echo [%date% %time%] main.py �����訫�� � �訡���.
    pause
    exit /b 1
)

echo [%date% %time%] ��⮢�.
pause
