@echo off
chcp 65001 >nul
title 局域网设备扫描工具

echo ==================================================
echo    局域网设备扫描工具 - Web版
echo ==================================================
echo.
echo 正在启动 Web 服务...
echo.

cd /d "%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo.
    pause
    exit /b 1
)

start "" http://127.0.0.1:5000
python lan_scanner_web.py

echo.
echo 服务已停止。
pause
