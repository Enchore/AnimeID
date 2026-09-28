@echo off
chcp 65001 >nul
title AnimeID Recognition System

echo.
echo  ============================================
echo   Anime Character Recognition System
echo   Deep Learning Project  ^|  v1.0
echo  ============================================
echo.

cd /d "%~dp0"

echo [1/3] Checking Python...
python --version 2>nul || (echo [ERROR] Python not found, install Python 3.9+ & pause & exit /b 1)

echo [2/3] Installing dependencies...
pip install -r requirements.txt -q --no-warn-script-location

echo [3/3] Starting web server...
echo.
echo  System online at: http://localhost:5000
echo  Dashboard:         http://localhost:5000/dashboard
echo  Press Ctrl+C to stop
echo.

python module3_web/app.py

pause
