@echo off
title LAN Scanner

echo ==================================================
echo    LAN Device Scanner - Web Edition
echo ==================================================
echo.
echo Starting web server (Python 3.12)...
echo.

cd /d "%~dp0"

py -3.12 --version > 2>
if errorlevel 1 (
    echo [ERROR] Python 3.12 not found. Please install Python 3.10+
    pause
    exit /b 1
)

py -3.12 -m pip show flask > 2>
if errorlevel 1 (
    echo Installing dependencies...
    py -3.12 -m pip install flask paramiko
)

echo.
echo Launching server on http://127.0.0.1:5800
start py -3.12 lan_scanner_web.py

REM Wait 3 seconds for server to start
ping 127.0.0.1 -n 3 >

start http://127.0.0.1:5800

echo.
echo Server is running. Check your browser.
echo Close this window to stop.
pause