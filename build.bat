@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo Lexy — Nuitka Windows Build
echo ========================================

REM === Configuration ===
set APP_NAME=Lexy
set MAIN_FILE=lexy_tray.py
set ICON_FILE=lexy.ico

REM === Auto-detect CPU cores ===
set CPU_CORES=%NUMBER_OF_PROCESSORS%
if not defined CPU_CORES set CPU_CORES=4
set /a BUILD_JOBS=%CPU_CORES%

REM === Module exclude list (safe to remove) ===
set EXCLUDE_MODULES=unittest,test,pytest,_pytest,doctest,pdb,pdbpp
set EXCLUDE_MODULES=%EXCLUDE_MODULES%,setuptools,pip,distutils,pkg_resources
set EXCLUDE_MODULES=%EXCLUDE_MODULES%,email.mime,http.server,xmlrpc,pydoc

echo.
echo [1/5] Cleaning old builds...
if exist build rd /s /q build
if exist "dist\%APP_NAME%.dist" rd /s /q "dist\%APP_NAME%.dist"

echo.
echo [2/5] Checking for icon...
if not exist "%ICON_FILE%" (
    echo WARNING: No %ICON_FILE% found. Creating a placeholder...
    REM Create simple 1x1 pixel ICO placeholder using PowerShell
    powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%TEMP%\_lexy_icon.lnk');$s.Save()" 2>nul
)

echo.
echo [3/5] Compiling with Nuitka (%CPU_CORES% threads, using Zig)...
echo This will take a while — 30-60 minutes depending on your machine.
echo.

python -m nuitka --standalone ^
    --assume-yes-for-downloads ^
    --zig ^
    --windows-console-mode=disable ^
    --lto=yes ^
    --jobs=%BUILD_JOBS% ^
    --enable-plugin=anti-bloat ^
    --noinclude-pytest-mode=nofollow ^
    --noinclude-setuptools-mode=nofollow ^
    --nofollow-import-to=%EXCLUDE_MODULES% ^
    --python-flag=no_docstrings ^
    --output-dir=dist ^
    --windows-icon-from-ico=%ICON_FILE% ^
    --remove-output ^
    --include-data-dir=frontends/templates=templates ^
    --include-data-dir=frontends/static=static ^
    --include-data-dir=whatsapp-bridge=whatsapp-bridge ^
    --include-data-files=.env.example=.env.example ^
    %MAIN_FILE%

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [4/5] Copying additional assets...
if exist "%ICON_FILE%" copy "%ICON_FILE%" "dist\%APP_NAME%.dist\" >nul
if exist ".env.example" copy ".env.example" "dist\%APP_NAME%.dist\" >nul

echo.
echo [5/5] Calculating size...
for /f %%a in ('powershell -NoProfile -Command "(Get-ChildItem -LiteralPath 'dist\%APP_NAME%.dist' -Recurse -File | Measure-Object -Property Length -Sum).Sum"') do set TOTAL_SIZE=%%a
set TOTAL_SIZE=%TOTAL_SIZE:,=%
set /a SIZE_MB=%TOTAL_SIZE% / 1048576
echo.
echo ========================================
echo Build complete!
echo Output: dist\%APP_NAME%.dist
echo Size: ~%SIZE_MB% MB
echo ========================================
echo.
echo Next step: 
echo   1. Download Inno Setup 6+ from https://jrsoftware.org/isdl.php
echo   2. Open installer.iss in Inno Setup and click Compile
echo   3. Installer will be in the installer\ folder
echo.
pause
