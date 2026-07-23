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

echo [4/6] Checking for old OCR dependencies...
set "HAS_EASYOCR=0"
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import easyocr" 2>nul
if not errorlevel 1 set "HAS_EASYOCR=1"

if "%HAS_EASYOCR%"=="1" (
    echo Old EasyOCR/PyTorch installation detected. Uninstalling...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip uninstall -y easyocr torch torchvision torchaudio 2>nul
    echo Old dependencies removed.
) else (
    echo No old EasyOCR installation found. Skipping uninstall.
)

:: Also clean any PaddleOCR 3.x leftovers that conflict with 2.x.
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip uninstall -y paddlex paddlepaddle 2>nul
echo OK.
echo.

echo [5/6] Installing base packages...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%~dp0requirements.txt"
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Retry with Aliyun mirror...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 exit /b 1
)
echo OK.
echo.

echo [6/6] Installing PaddleOCR 2.x and PaddlePaddle 2.x...

:: Clean potentially corrupted model cache from previous installs.
if exist "%USERPROFILE%\.paddleocr" (
    echo Cleaning old PaddleOCR model cache...
    rmdir /s /q "%USERPROFILE%\.paddleocr" 2>nul
)

set "HAS_NVIDIA=0"
nvidia-smi >nul 2>&1
if not errorlevel 1 set "HAS_NVIDIA=1"

:: Uninstall packages that might have been compiled against numpy 2.x
:: so PaddleOCR can pull compatible versions fresh.
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip uninstall -y scipy scikit-image 2>nul

set "PADDLE_PKG=paddlepaddle==2.6.2"
if "%HAS_NVIDIA%"=="1" (
    echo NVIDIA GPU detected — using GPU build.
    set "PADDLE_PKG=paddlepaddle-gpu==2.6.2"
) else (
    echo No NVIDIA GPU found — using CPU build.
)

:: numpy<2.0 MUST be installed before PaddlePaddle because PaddlePaddle
:: 2.6.2's C extensions are compiled against numpy 1.x ABI.
echo Installing numpy 1.x + PaddlePaddle 2.6.2 + PaddleOCR 2.7.3...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install "numpy>=1.26.0,<2.0.0"
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install %PADDLE_PKG% paddleocr==2.7.3
if errorlevel 1 (
    echo [WARN] Install failed. Trying CPU PaddlePaddle as fallback...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install paddlepaddle==2.6.2 paddleocr==2.7.3
    if errorlevel 1 exit /b 1
)

echo Verifying PaddleOCR installation...
"%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --ocr
if errorlevel 1 exit /b 1
echo OK.
echo.

echo Verifying OCR GPU status...
if "%HAS_NVIDIA%"=="1" (
    "%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --paddle-cuda-required
    if errorlevel 1 exit /b 1
) else (
    "%PYTHON_EXE%" %PYTHON_ARGS% setup_env_check.py --paddle-cuda
)
echo.
echo ========================================
if "%HAS_NVIDIA%"=="1" (
    echo   Setup complete. PaddleOCR GPU acceleration is ready.
) else (
    echo   Setup complete. PaddleOCR will use CPU because no NVIDIA GPU was detected.
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
