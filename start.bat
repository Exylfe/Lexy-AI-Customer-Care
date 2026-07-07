@echo off
title Lexy — AI Assistant
echo ============================================
echo   Lexy — AI Assistant Launcher
echo ============================================
echo.
echo  1) Terminal Chat
echo  2) Web Dashboard (port 5050)
echo  3) Terminal + Dashboard
echo  4) WhatsApp Bridge (requires bridge)
echo  5) All Services
echo.
set /p choice="Select [1-5]: "

if "%choice%"=="1" (
    python main.py
) else if "%choice%"=="2" (
    python main.py --web
) else if "%choice%"=="3" (
    python main.py --all
) else if "%choice%"=="4" (
    start python frontends/whatsapp_server.py
    start cmd /k "cd whatsapp-bridge && node index.js"
) else if "%choice%"=="5" (
    start python main.py --all
    start python frontends/whatsapp_server.py
    timeout /t 3 >nul
    start cmd /k "cd whatsapp-bridge && node index.js"
) else (
    echo Invalid choice
    timeout /t 2 >nul
)
