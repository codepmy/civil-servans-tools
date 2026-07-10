@echo off
chcp 65001 >nul
echo ========================================
echo    PDF格式转换器 - 环境安装程序
echo ========================================
echo.

REM 检查 Python
echo [1/3] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10 或更高版本。
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)
python --version
echo Python 环境正常。
echo.

REM 升级 pip
echo [2/3] 升级 pip...
python -m pip install --upgrade pip -q
echo pip 升级完成。
echo.

REM 安装依赖
echo [3/3] 安装项目依赖（可能需要几分钟）...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [警告] 部分依赖安装失败，请检查网络连接后重试。
    pause
    exit /b 1
)
echo.
echo ========================================
echo   安装完成！
echo   双击 run.bat 启动程序。
echo ========================================
pause
