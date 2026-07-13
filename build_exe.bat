@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYINSTALLER_CMD="
where pyinstaller >nul 2>&1
if not errorlevel 1 set "PYINSTALLER_CMD=pyinstaller"

if not defined PYINSTALLER_CMD (
    python -m PyInstaller --version >nul 2>&1
    if not errorlevel 1 set "PYINSTALLER_CMD=python -m PyInstaller"
)

if not defined PYINSTALLER_CMD (
    echo [ERROR] PyInstaller was not found.
    echo Please run: python -m pip install pyinstaller
    pause
    exit /b 1
)

%PYINSTALLER_CMD% --clean --noconfirm main.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Please check the log above.
    pause
    exit /b 1
)

echo.
echo Build complete. Check the dist folder.
pause
