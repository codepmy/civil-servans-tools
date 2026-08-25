"""开机自启动管理（Windows HKCU Run 键，无需管理员权限）。

写入注册表 ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
下名为 ``CivilServantsTools`` 的值，值为带 ``--autostart`` 参数的启动命令，
程序以此参数启动时后台运行到系统托盘（不显示主窗口）。
"""

from __future__ import annotations

import sys
import winreg

from app_paths import app_root

APP_KEY_NAME = "CivilServantsTools"  # Run 键下的值名
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _build_launch_command() -> str:
    """构建写入注册表的启动命令。

    - 打包版（sys.frozen）：exe 路径 + --autostart
    - 源码运行：python.exe + main.py 绝对路径 + --autostart

    所有路径均用双引号包裹（防空格/中文路径），注册表值用 REG_SZ（Unicode）。
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --autostart'
    main_py = app_root() / "main.py"  # 源码模式下 app_root() = 项目根目录
    return f'"{sys.executable}" "{main_py}" --autostart'


def is_enabled() -> bool:
    """自启动是否开启。

    与当前命令严格比对——exe 被移动/改名后返回 False，重新勾选即修复。
    读取失败一律按未开启处理，不抛异常。
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, APP_KEY_NAME)
    except FileNotFoundError:
        return False  # 键/值不存在 → 未开启
    except OSError:
        return False  # 读取失败按未开启处理
    return value == _build_launch_command()


def enable() -> bool:
    """写入 Run 键（已存在则覆盖）。返回是否成功。"""
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(
                key, APP_KEY_NAME, 0, winreg.REG_SZ, _build_launch_command()
            )
        return True
    except OSError:
        return False


def disable() -> bool:
    """删除 Run 键值。返回是否成功（本来就没有也算成功）。"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_KEY_NAME)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False
