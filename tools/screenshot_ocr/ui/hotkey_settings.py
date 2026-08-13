"""快捷键自定义对话框。

允许用户设置截图 OCR 的全局快捷键，修改后即时保存到
``user_config.json`` 并重新注册。
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget,
)

from tools.screenshot_ocr.core.hotkey_manager import HotkeyManager


# Qt.Key → 人类可读键名
def _qt_key_to_name(qt_key: int) -> str:
    """将 Qt.Key 枚举值转为 VK_BY_NAME 兼容的键名。"""
    if Qt.Key.Key_A <= qt_key <= Qt.Key.Key_Z:
        return chr(qt_key).upper()
    if Qt.Key.Key_0 <= qt_key <= Qt.Key.Key_9:
        return chr(qt_key)
    if Qt.Key.Key_F1 <= qt_key <= Qt.Key.Key_F24:
        return f"F{qt_key - Qt.Key.Key_F1.value + 1}"
    special: dict[int, str] = {
        Qt.Key.Key_Space.value:      "SPACE",
        Qt.Key.Key_Tab.value:        "TAB",
        Qt.Key.Key_Backspace.value:  "BACK",
        Qt.Key.Key_Delete.value:     "DELETE",
        Qt.Key.Key_Insert.value:     "INSERT",
        Qt.Key.Key_Home.value:       "HOME",
        Qt.Key.Key_End.value:        "END",
        Qt.Key.Key_PageUp.value:     "PRIOR",
        Qt.Key.Key_PageDown.value:   "NEXT",
        Qt.Key.Key_Left.value:       "LEFT",
        Qt.Key.Key_Right.value:      "RIGHT",
        Qt.Key.Key_Up.value:         "UP",
        Qt.Key.Key_Down.value:       "DOWN",
        Qt.Key.Key_Escape.value:     "ESCAPE",
        Qt.Key.Key_Pause.value:      "PAUSE",
        Qt.Key.Key_Print.value:      "SNAPSHOT",
    }
    return special.get(qt_key, "")


class _KeyCaptureButton(QPushButton):
    """点击后进入"捕获模式"的按钮 — 显示为输入框风格。

    进入捕获模式后，下一次按键（包括组合键中的基础键）即为目标键。
    """

    key_captured = pyqtSignal(str)  # 键名

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._capturing = False
        self.setCheckable(True)
        self.setFixedWidth(70)
        self.toggled.connect(self._on_toggle)
        self._update_style()

    def _on_toggle(self, checked: bool) -> None:
        self._capturing = checked
        if checked:
            self.setText("…")
        self._update_style()

    def capture_key(self, qt_key: int) -> bool:
        """处理一次按键捕获。返回 True 表示捕获成功。"""
        if not self._capturing:
            return False
        name = _qt_key_to_name(qt_key)
        if not name:
            return False
        self.setText(name)
        self.setChecked(False)
        self._capturing = False
        self._update_style()
        self.key_captured.emit(name)
        return True

    def _update_style(self) -> None:
        if self._capturing:
            self.setStyleSheet(
                "QPushButton { background: #EEF2FF; border: 2px solid #4F46E5; "
                "border-radius: 6px; padding: 4px 8px; font-size: 14px; "
                "font-weight: 600; color: #4F46E5; }"
            )
        else:
            self.setStyleSheet(
                "QPushButton { background: #FFFFFF; border: 1px solid #D1D5DB; "
                "border-radius: 6px; padding: 4px 8px; font-size: 14px; "
                "font-weight: 600; color: #1F2937; }"
                "QPushButton:hover { border-color: #4F46E5; }"
            )


# ═══════════════════════════════════════════════════════════════════════
# 设置对话框
# ═══════════════════════════════════════════════════════════════════════


class HotkeySettingsDialog(QDialog):
    """截图 OCR 快捷键设置对话框。"""

    hotkey_changed = pyqtSignal(list, str)  # (mod_list, key_name)

    # 默认快捷键
    DEFAULT_MOD_LIST = ["ctrl", "shift"]
    DEFAULT_KEY = "Z"

    def __init__(
        self,
        current_mod_list: list[str] | None = None,
        current_key: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setMinimumWidth(360)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._current_mod_list = (
            list(current_mod_list) if current_mod_list is not None
            else list(self.DEFAULT_MOD_LIST)
        )
        self._current_key = (
            current_key if current_key is not None
            else self.DEFAULT_KEY
        )

        self._setup_ui()
        self._sync_ui_from_state()

    # ── UI ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # 标题
        title = QLabel("截图 OCR 快捷键")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #1F2937;")
        layout.addWidget(title)

        # 修饰键行
        mod_row = QHBoxLayout()
        mod_row.setSpacing(10)
        mod_label = QLabel("修饰键：")
        mod_label.setStyleSheet("font-size: 13px; color: #374151;")
        mod_row.addWidget(mod_label)

        self._chk_ctrl  = QCheckBox("Ctrl")
        self._chk_alt   = QCheckBox("Alt")
        self._chk_shift = QCheckBox("Shift")
        self._chk_win   = QCheckBox("Win")
        for chk in (self._chk_ctrl, self._chk_alt, self._chk_shift, self._chk_win):
            chk.setStyleSheet("font-size: 13px; color: #1F2937;")
            chk.toggled.connect(self._update_preview)
            mod_row.addWidget(chk)
        mod_row.addStretch()
        layout.addLayout(mod_row)

        # 按键行
        key_row = QHBoxLayout()
        key_row.setSpacing(10)
        key_label = QLabel("按键：")
        key_label.setStyleSheet("font-size: 13px; color: #374151;")
        key_row.addWidget(key_label)

        self._key_btn = _KeyCaptureButton(self._current_key)
        self._key_btn.key_captured.connect(self._on_key_captured)
        key_row.addWidget(self._key_btn)
        key_row.addStretch()
        layout.addLayout(key_row)

        # 预览
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #4F46E5; "
            "background: #EEF2FF; border-radius: 8px; padding: 10px;"
        )
        layout.addWidget(self._preview_label)

        layout.addStretch()

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        restore_btn = QPushButton("恢复默认")
        restore_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; color: #374151; border: 1px solid #D1D5DB; "
            "border-radius: 6px; padding: 6px 14px; font-size: 13px; }"
            "QPushButton:hover { background: #E5E7EB; }"
        )
        restore_btn.clicked.connect(self._restore_default)
        btn_row.addWidget(restore_btn)
        btn_row.addStretch()

        # OK / Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_ok)
        button_box.rejected.connect(self.reject)
        btn_row.addWidget(button_box)
        layout.addLayout(btn_row)

    # ── Logic ───────────────────────────────────────────────────────

    def _sync_ui_from_state(self) -> None:
        """将 current 状态同步到 UI。"""
        self._chk_ctrl.setChecked("ctrl" in self._current_mod_list)
        self._chk_alt.setChecked("alt" in self._current_mod_list)
        self._chk_shift.setChecked("shift" in self._current_mod_list)
        self._chk_win.setChecked("win" in self._current_mod_list)
        self._key_btn.setText(self._current_key)
        self._update_preview()

    def _get_modifiers_from_ui(self) -> list[str]:
        """从复选框组装修饰键列表。"""
        mod_list: list[str] = []
        if self._chk_ctrl.isChecked():
            mod_list.append("ctrl")
        if self._chk_alt.isChecked():
            mod_list.append("alt")
        if self._chk_shift.isChecked():
            mod_list.append("shift")
        if self._chk_win.isChecked():
            mod_list.append("win")
        return mod_list

    def _update_preview(self) -> None:
        """更新预览标签文字。"""
        parts: list[str] = []
        if self._chk_ctrl.isChecked():
            parts.append("Ctrl")
        if self._chk_alt.isChecked():
            parts.append("Alt")
        if self._chk_shift.isChecked():
            parts.append("Shift")
        if self._chk_win.isChecked():
            parts.append("Win")
        parts.append(self._key_btn.text() or self._current_key)
        self._preview_label.setText(" + ".join(parts))

    def _on_key_captured(self, key_name: str) -> None:
        self._current_key = key_name
        self._update_preview()

    def _restore_default(self) -> None:
        self._current_mod_list = list(self.DEFAULT_MOD_LIST)
        self._current_key = self.DEFAULT_KEY
        self._sync_ui_from_state()

    def _on_ok(self) -> None:
        mod_list = self._get_modifiers_from_ui()
        if not mod_list:
            return  # 至少需要一个修饰键
        if not self._current_key:
            return
        self.hotkey_changed.emit(mod_list, self._current_key)
        self.accept()

    # ── 按键捕获 ────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return
        # 优先让按键捕获按钮处理
        if self._key_btn.capture_key(int(event.key())):
            return
        # Esc 关闭
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
