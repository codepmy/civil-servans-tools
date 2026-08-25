"""统一设置对话框。

集中管理应用级偏好：
1. 截图 OCR 快捷键（复用 HotkeySettingsDialog，点「确定」才生效并即时注册）
2. 开机自启动（勾选即写注册表 HKCU Run 键）
3. 关闭窗口行为（最小化到托盘 / 退出程序，写入 user_config.json 的 close_action）

所有设置项修改即生效，对话框仅提供「关闭」按钮。

注意：本模块通过回调注入与 MainWindow 解耦——MainWindow import 本模块，
本模块绝不能 import ui.main_window（会循环导入）。
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from tools.autostart.core import autostart
from tools.screenshot_ocr.ui.hotkey_settings import HotkeySettingsDialog

# 与 ui/main_window.py 的 PRIMARY_BUTTON_STYLE 保持一致
# （勿 import main_window，会循环导入）
_CLOSE_BTN_STYLE = (
    "QPushButton { background-color: #4F46E5; color: #FFFFFF; border: none; "
    "border-radius: 6px; padding: 6px 20px; font-size: 13px; font-weight: 600; min-height: 28px; }"
    "QPushButton:hover { background-color: #4338CA; }"
    "QPushButton:pressed { background-color: #3730A3; }"
)

_MOD_NAMES = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}


def format_hotkey(mod_list: list[str], key: str) -> str:
    """将修饰键列表与键名格式化为可读文本。

    ``['ctrl', 'shift']`` + ``'Z'`` → ``'Ctrl + Shift + Z'``
    """
    parts = [_MOD_NAMES.get(m, m) for m in mod_list]
    parts.append(str(key))
    return " + ".join(parts)


class SettingsDialog(QDialog):
    """统一设置对话框。所有设置项修改即生效，仅提供「关闭」按钮。"""

    def __init__(
        self,
        initial_mod_list: list[str],                          # 当前 OCR 热键修饰键
        initial_key: str,                                     # 当前 OCR 热键键名
        initial_close_action: str = "",                       # 'quit'/'tray'/''（来自 MainWindow._load_close_action）
        on_hotkey_changed: Callable[[list[str], str], None] | None = None,   # MainWindow 接 self._socr_mgr.set_hotkey
        on_close_action_changed: Callable[[str], None] | None = None,        # MainWindow 接 self._save_close_action
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(440)
        self.setWindowFlags(
            self.windowFlags() & ~self.windowFlags().WindowContextHelpButtonHint
        )

        self._mod_list = list(initial_mod_list)
        self._key = initial_key
        self._on_hotkey_changed = on_hotkey_changed
        self._on_close_action_changed = on_close_action_changed

        self._setup_ui(initial_close_action)

    # ── UI ──────────────────────────────────────────────────────────

    def _setup_ui(self, initial_close_action: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # ── 区块 1：截图 OCR 快捷键 ──
        gb_hotkey = QGroupBox("截图 OCR 快捷键")
        hotkey_row = QHBoxLayout(gb_hotkey)
        hotkey_row.setContentsMargins(0, 12, 0, 8)
        hotkey_row.setSpacing(10)

        self._hotkey_label = QLabel(format_hotkey(self._mod_list, self._key))
        self._hotkey_label.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #4F46E5; "
            "background: #EEF2FF; border-radius: 6px; padding: 5px 12px;"
        )
        hotkey_row.addWidget(self._hotkey_label)
        hotkey_row.addStretch()

        btn_modify = QPushButton("修改...")
        btn_modify.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_modify.clicked.connect(self._open_hotkey_dialog)
        hotkey_row.addWidget(btn_modify)
        layout.addWidget(gb_hotkey)

        # ── 区块 2：开机自启动 ──
        gb_auto = QGroupBox("开机自启动")
        auto_col = QVBoxLayout(gb_auto)
        auto_col.setContentsMargins(0, 12, 0, 8)
        auto_col.setSpacing(6)

        self._chk_autostart = QCheckBox("开机时自动启动（后台运行到系统托盘，不显示主窗口）")
        self._chk_autostart.setChecked(autostart.is_enabled())  # 打开对话框时读注册表
        self._chk_autostart.toggled.connect(self._on_autostart_toggled)
        auto_col.addWidget(self._chk_autostart)

        hint_auto = QLabel("提示：若被安全软件拦截，可在「任务管理器 → 启动」中手动启用本程序。")
        hint_auto.setWordWrap(True)
        hint_auto.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        auto_col.addWidget(hint_auto)
        layout.addWidget(gb_auto)

        # ── 区块 3：关闭窗口时 ──
        gb_close = QGroupBox("关闭窗口时")
        close_col = QVBoxLayout(gb_close)
        close_col.setContentsMargins(0, 12, 0, 8)
        close_col.setSpacing(6)

        self._radio_tray = QRadioButton("最小化到系统托盘")
        self._radio_quit = QRadioButton("退出程序")
        # 初始状态：'quit' → 退出；其余（含未设置过）→ 托盘（与 closeEvent 默认一致）
        self._radio_tray.setChecked(initial_close_action != "quit")
        self._radio_quit.setChecked(initial_close_action == "quit")
        # 先 setChecked 再 connect，避免初始化触发写入
        self._radio_tray.toggled.connect(self._on_close_action_toggled)
        close_col.addWidget(self._radio_tray)
        close_col.addWidget(self._radio_quit)
        layout.addWidget(gb_close)

        layout.addStretch()

        # ── 底部「关闭」按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setMinimumWidth(100)
        btn_close.setStyleSheet(_CLOSE_BTN_STYLE)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    # ── 快捷键 ──────────────────────────────────────────────────────

    def _open_hotkey_dialog(self) -> None:
        """打开快捷键子对话框（复用 HotkeySettingsDialog，点「确定」才生效）。"""
        dlg = HotkeySettingsDialog(
            current_mod_list=self._mod_list,
            current_key=self._key,
            parent=self,
        )

        def _apply(mod_list: list[str], key: str) -> None:
            self._mod_list = list(mod_list)
            self._key = key
            self._hotkey_label.setText(format_hotkey(mod_list, key))  # 刷新本窗口显示
            if self._on_hotkey_changed is not None:
                self._on_hotkey_changed(mod_list, key)  # → socr_mgr.set_hotkey（注册+持久化）

        dlg.hotkey_changed.connect(_apply)
        dlg.exec()

    # ── 开机自启动 ──────────────────────────────────────────────────

    def _on_autostart_toggled(self, checked: bool) -> None:
        """勾选/取消勾选 → 立即写注册表；失败则回滚勾选并警告。"""
        ok = autostart.enable() if checked else autostart.disable()
        if ok:
            return
        self._chk_autostart.blockSignals(True)  # 回滚时不触发二次写入
        self._chk_autostart.setChecked(not checked)
        self._chk_autostart.blockSignals(False)
        QMessageBox.warning(
            self,
            "开机自启动",
            "设置失败：注册表写入被拒绝。\n"
            "可能被杀毒软件或系统策略拦截，"
            "可手动在「任务管理器 → 启动」中添加本程序。",
        )

    # ── 关闭窗口行为 ────────────────────────────────────────────────

    def _on_close_action_toggled(self) -> None:
        """单选切换 → 立即写 user_config.json 的 close_action 字段。"""
        if self._on_close_action_changed is None:
            return
        value = "tray" if self._radio_tray.isChecked() else "quit"
        self._on_close_action_changed(value)  # → MainWindow._save_close_action
