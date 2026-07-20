@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "SETUP_LOG=%~dp0setup.log"
if /I "%~1"=="--run" goto main

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_runner.ps1" -ScriptPath "%~f0" -LogPath "%SETUP_LOG%"
set "SETUP_EXIT=%ERRORLEVEL%"
echo.
echo Log saved to: %SETUP_LOG%
if not "%SETUP_EXIT%"=="0" (
    echo.
    echo Setup failed. Read setup.log above for details.
)
pause
exit /b %SETUP_EXIT%

:main
if not defined PYTORCH_CUDA_INDEX_URL set "PYTORCH_CUDA_INDEX_URL=https://download.pytorch.org/whl/cu128"

echo ========================================
echo   CivilServantsTools - Setup
echo ========================================
echo.

echo [1/6] Checking Python...
call :find_python
if errorlevel 1 exit /b 1

echo Python command: "%PYTHON_EXE%" %PYTHON_ARGS%
"%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --python
if errorlevel 1 exit /b 1
echo OK.
echo.

echo [2/6] Upgrading pip...
"%PYTHON_EXE%" %PYTHON_ARGS% -m ensurepip --upgrade
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --upgrade pip
if errorlevel 1 exit /b 1
echo OK.
echo.

echo [3/6] Setting PyPI mirror...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 echo [WARN] Failed to set mirror. Continuing.
echo OK.
echo.

echo [4/6] Installing base packages...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Retry with Aliyun mirror...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 exit /b 1
)
echo OK.
echo.

echo [5/6] Installing PyTorch for OCR...
set "HAS_NVIDIA=0"
nvidia-smi >nul 2>&1
if not errorlevel 1 set "HAS_NVIDIA=1"

if "%HAS_NVIDIA%"=="1" (
    echo NVIDIA GPU detected.
    echo Installing CUDA-enabled PyTorch. CPU PyTorch will not be accepted.
    echo PyTorch CUDA index: %PYTORCH_CUDA_INDEX_URL%
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip uninstall -y torch torchvision torchaudio
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --no-cache-dir --force-reinstall torch torchvision --index-url %PYTORCH_CUDA_INDEX_URL% --trusted-host download.pytorch.org
    if errorlevel 1 (
        echo [ERROR] CUDA PyTorch install failed.
        echo Fix suggestions:
        echo   1. Confirm setup is using Python 3.12 x64 in the Python command above.
        echo   2. Re-run setup.bat with VPN if download.pytorch.org is blocked.
        echo   3. Keep PYTORCH_CUDA_INDEX_URL=https://download.pytorch.org/whl/cu128 for RTX 50 series.
        exit /b 1
    )
    "%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --cuda-required
    if errorlevel 1 exit /b 1
) else (
    echo No NVIDIA GPU found. Installing CPU PyTorch.
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --upgrade torch torchvision
    if errorlevel 1 exit /b 1
    "%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --cuda
)
echo OK.
echo.

echo [6/6] Installing EasyOCR...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --upgrade "easyocr>=1.7.0,<2.0.0"
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --ocr
if errorlevel 1 exit /b 1
echo OK.
echo.

echo Verifying OCR GPU status...
if "%HAS_NVIDIA%"=="1" (
    "%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --cuda-required
    if errorlevel 1 exit /b 1
) else (
    "%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --cuda
)
echo.
echo ========================================
if "%HAS_NVIDIA%"=="1" (
    echo   Setup complete. OCR GPU acceleration is ready.
) else (
    echo   Setup complete. OCR will use CPU because no NVIDIA GPU was detected.
)
echo ========================================
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

echo [ERROR] Python was not found.
echo Install Python 3.12 x64 and enable Add python.exe to PATH or Python Launcher.
exit /b 1
