@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

call :find_python
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Please install Python 3.12 x64 and run setup.bat first.
    pause
    exit /b 1
)

set "PYINSTALLER_CMD="
where pyinstaller >nul 2>&1
if not errorlevel 1 set "PYINSTALLER_CMD=pyinstaller"

if not defined PYINSTALLER_CMD (
    "%PYTHON_EXE%" %PYTHON_ARGS% -m PyInstaller --version >nul 2>&1
    if not errorlevel 1 set "PYINSTALLER_CMD=""%PYTHON_EXE%"" %PYTHON_ARGS% -m PyInstaller"
)

if not defined PYINSTALLER_CMD (
    echo [ERROR] PyInstaller was not found.
    echo Please run: "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install pyinstaller
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
exit /b 0

:find_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

for %%P in ("%LocalAppData%\Programs\Python\Python312\python.exe" "%ProgramFiles%\Python312\python.exe" "%ProgramFiles(x86)%\Python312\python.exe") do (
    if exist "%%~P" (
        set "PYTHON_EXE=%%~P"
        exit /b 0
    )
)

py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3.12"
    exit /b 0
)

python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    exit /b 0
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
    exit /b 0
)

exit /b 1
