@echo off
title LAN Scanner

echo ==================================================
echo    LAN Device Scanner - Web Edition
echo ==================================================
echo.
echo Starting web server...
echo.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

pip show flask >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install flask paramiko
)

echo.
echo Launching server on http://127.0.0.1:5000
start python lan_scanner_web.py

REM Wait 3 seconds for server to start
ping 127.0.0.1 -n 3 >nul

start http://127.0.0.1:5000

echo.
echo Server is running. Check your browser.
echo Close this window to stop.
pause
