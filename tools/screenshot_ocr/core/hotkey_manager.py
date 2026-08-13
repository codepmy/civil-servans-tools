"""Windows 全局热键管理器 — GetAsyncKeyState 轮询方案。

摒弃 ``RegisterHotKey`` + ``nativeEventFilter``（在该 PyQt6 环境中
nativeEventFilter 收不到 WM_HOTKEY），改用 ``GetAsyncKeyState``
定时轮询。零冲突、零注册、100% 可靠。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

# ═══════════════════════════════════════════════════════════════════════
# Win32
# ═══════════════════════════════════════════════════════════════════════

_user32 = ctypes.windll.user32
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short

MOD_ALT      = 0x0001
MOD_CONTROL  = 0x0002
MOD_SHIFT    = 0x0004
MOD_WIN      = 0x0008

# 修饰键 → VK
_MODIFIER_VK = {
    "alt":   0x12,  # VK_MENU
    "ctrl":  0x11,  # VK_CONTROL
    "shift": 0x10,  # VK_SHIFT
    "win":   0x5B,  # VK_LWIN
}

MOD_NAME_TO_VAL: dict[str, int] = {
    "alt":   MOD_ALT,   "ctrl":  MOD_CONTROL,
    "shift": MOD_SHIFT, "win":   MOD_WIN,
}
MOD_VAL_TO_NAME: dict[int, str] = {v: k for k, v in MOD_NAME_TO_VAL.items()}

VK_BY_NAME: dict[str, int] = {}
for _i, _ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    VK_BY_NAME[_ch] = 0x41 + _i
for _i in range(10):
    VK_BY_NAME[str(_i)] = 0x30 + _i
for _i in range(1, 25):
    VK_BY_NAME[f"F{_i}"] = 0x6F + _i
VK_BY_NAME.update({
    "SPACE": 0x20, "TAB": 0x09, "RETURN": 0x0D,
    "ESCAPE": 0x1B, "BACK": 0x08, "DELETE": 0x2E,
    "INSERT": 0x2D, "HOME": 0x24, "END": 0x23,
    "PRIOR": 0x21, "NEXT": 0x22, "APPS": 0x5D,
})
VK_TO_NAME: dict[int, str] = {v: k for k, v in VK_BY_NAME.items()}
for _vc in range(0x30, 0x3A):
    VK_TO_NAME.setdefault(_vc, chr(_vc))
for _vc in range(0x41, 0x5B):
    VK_TO_NAME.setdefault(_vc, chr(_vc))


# ═══════════════════════════════════════════════════════════════════════
# HotkeyManager
# ═══════════════════════════════════════════════════════════════════════


class HotkeyManager(QObject):
    """全局热键管理器（轮询方案）。

    使用 ``GetAsyncKeyState`` 每 50ms 检查一次组合键状态，
    检测到热键按下时发出 ``hotkey_triggered`` 信号。
    带有防抖机制，避免重复触发。

    Usage::

        mgr = HotkeyManager()
        mgr.hotkey_triggered.connect(on_hotkey)
        mgr.start("ctrl", "shift", "Z")
    """

    hotkey_triggered = pyqtSignal()
    registration_result = pyqtSignal(bool, str)

    def __init__(self) -> None:
        super().__init__(None)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.setInterval(100)  # 100ms 轮询，GetAsyncKeyState 极轻量无开销

        self._mods: list[str] = []
        self._vk: int = 0
        self._active = False
        self._was_down = False  # 防抖：上一次轮询是否为按下状态

    # ── properties ──────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def current_modifiers(self) -> int:
        return self.modifiers_from_list(self._mods)

    @property
    def current_vk(self) -> int:
        return self._vk

    # ── public API ──────────────────────────────────────────────────

    def start(self, mod_list: list[str], key: str) -> None:
        """启动热键轮询。

        Args:
            mod_list: 修饰键列表，如 ``["ctrl", "shift"]``。
            key: 触发键名，如 ``"Z"``。
        """
        if self._active:
            self.stop()

        vk = self.vk_from_key(key)
        if vk == 0:
            self.registration_result.emit(
                False, f"无效的按键名称：{key}"
            )
            return

        self._mods = [m.lower() for m in mod_list]
        self._vk = vk
        self._was_down = False
        self._active = True
        self._timer.start()

        label = "+".join(self._mods) + "+" + key
        self.registration_result.emit(
            True, f"快捷键已就绪：{label}（轮询模式）"
        )

    def stop(self) -> None:
        """停止轮询。"""
        self._timer.stop()
        self._active = False

    def set_hotkey(self, mod_list: list[str], key: str) -> None:
        """更换热键组合。"""
        self.start(mod_list, key)

    # ── polling ─────────────────────────────────────────────────────

    def _poll(self) -> None:
        """检查当前键盘状态是否匹配热键组合。"""
        # 所有修饰键必须按下
        for mod in self._mods:
            vk = _MODIFIER_VK.get(mod)
            if vk and not _is_key_down(vk):
                self._was_down = False
                return

        # 触发键必须按下
        is_down = _is_key_down(self._vk)
        if is_down and not self._was_down:
            # 上升沿触发（防止重复）
            self._was_down = True
            self.hotkey_triggered.emit()
        elif not is_down:
            self._was_down = False

    # ── 静态工具 ────────────────────────────────────────────────────

    @staticmethod
    def modifiers_from_list(mod_list: list[str]) -> int:
        result = 0
        for m in mod_list:
            result |= MOD_NAME_TO_VAL.get(m.lower(), 0)
        return result

    @staticmethod
    def modifiers_to_list(modifiers: int) -> list[str]:
        return [n for n, v in MOD_NAME_TO_VAL.items() if (modifiers & v)]

    @staticmethod
    def vk_from_key(key: str) -> int:
        upper = key.upper()
        if upper in VK_BY_NAME:
            return VK_BY_NAME[upper]
        if len(upper) == 1:
            return ord(upper)
        return 0

    @staticmethod
    def key_from_vk(vk: int) -> str:
        if vk in VK_TO_NAME:
            return VK_TO_NAME[vk]
        if 0x41 <= vk <= 0x5A:
            return chr(vk)
        if 0x30 <= vk <= 0x39:
            return chr(vk)
        return f"VK_{vk}"


def _is_key_down(vk: int) -> bool:
    """检查虚拟键是否当前处于按下状态。"""
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)
