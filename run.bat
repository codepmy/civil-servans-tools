@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

call :find_python
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Please run setup.bat after installing Python 3.12 x64.
    pause
    exit /b 1
)

echo Using Python: "%PYTHON_EXE%" %PYTHON_ARGS%
"%PYTHON_EXE%" %PYTHON_ARGS% main.py
pause
exit /b %ERRORLEVEL%

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
