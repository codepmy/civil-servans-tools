"""浮动 Toast 通知 — 屏幕右下角弹出，自动淡出消失。

支持三种变体：成功 / 警告 / 错误。
"""

from __future__ import annotations

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve,
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QWidget,
)

# ── 图标 + 颜色预设 ────────────────────────────────────────────────────

_VARIANTS = {
    "success": {
        "icon":  "✅",
        "bg":    "#ECFDF5",
        "border":"#6EE7B7",
        "text":  "#065F46",
    },
    "warning": {
        "icon":  "⚠️",
        "bg":    "#FFFBEB",
        "border":"#FCD34D",
        "text":  "#92400E",
    },
    "error": {
        "icon":  "❌",
        "bg":    "#FEF2F2",
        "border":"#FCA5A5",
        "text":  "#991B1B",
    },
}


class Toast(QWidget):
    """屏幕右下角浮层通知 — 自动消失。

    Usage::

        Toast.show_message("识别完成，已复制到剪贴板", variant="success")
        Toast.show_message("OCR 环境未就绪", variant="error")

    所有方法都是静态的，无需手动维护实例。
    """

    _instances: list[Toast] = []

    # ── public API ──────────────────────────────────────────────────

    @classmethod
    def show_message(
        cls,
        text: str,
        variant: str = "success",
        duration_ms: int = 3000,
    ) -> None:
        """弹出 toast 通知。

        Args:
            text: 通知文字。
            variant: ``"success"`` | ``"warning"`` | ``"error"``。
            duration_ms: 显示时长（毫秒），默认 3 秒。
        """
        toast = cls(text, variant, duration_ms)
        cls._instances.append(toast)
        toast.show()

    # ── internals ───────────────────────────────────────────────────

    def __init__(
        self, text: str, variant: str, duration_ms: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._duration_ms = duration_ms
        self._opacity_effect: QGraphicsOpacityEffect | None = None

        style = _VARIANTS.get(variant, _VARIANTS["success"])

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setStyleSheet(
            f"Toast {{ background: {style['bg']}; "
            f"border: 1px solid {style['border']}; "
            f"border-radius: 8px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        icon_label = QLabel(style["icon"])
        icon_label.setStyleSheet("font-size: 16px; background: transparent; border: none;")
        layout.addWidget(icon_label)

        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            f"color: {style['text']}; font-size: 13px; "
            f"background: transparent; border: none;"
        )
        font = QFont()
        font.setPixelSize(13)
        text_label.setFont(font)
        layout.addWidget(text_label)

        self.adjustSize()
        self._position_on_screen()

        # 淡入动画
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 淡出动画
        self._fade_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_out.setDuration(300)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(self._on_fade_out_finished)

        self._fade_in.start()

        # 自动消失计时器
        QTimer.singleShot(self._duration_ms, self._start_fade_out)

    def _position_on_screen(self) -> None:
        """定位到主屏右下角。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.right() - self.width() - 20
        y = geo.bottom() - self.height() - 20
        self.move(QPoint(x, y))

    def _start_fade_out(self) -> None:
        self._fade_out.start()

    def _on_fade_out_finished(self) -> None:
        self.hide()
        self.deleteLater()
        if self in self._instances:
            self._instances.remove(self)
