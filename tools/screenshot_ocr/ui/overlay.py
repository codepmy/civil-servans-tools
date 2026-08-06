"""全屏截图选区覆盖层。

截取全屏 → 半透明遮罩 → 鼠标拖拽矩形选区 → 自动确认关闭 →
发出 ``captured`` 信号携带选区像素。
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import (
    QPoint, QRect, QRectF, Qt, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QCursor, QFont, QImage,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import QApplication, QWidget


class ScreenshotOverlay(QWidget):
    """全屏截图选区控件。

    Usage::

        overlay = ScreenshotOverlay()
        overlay.captured.connect(on_captured)
        overlay.cancelled.connect(on_cancelled)
        overlay.start()
    """

    captured = pyqtSignal(np.ndarray)  # RGB uint8 数组
    cancelled = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._screenshot: QPixmap | None = None
        self._origin: QPoint | None = None
        self._current_rect: QRect | None = None
        self._confirmed = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(_build_crosshair_cursor())
        self.setMouseTracking(True)

    # ── Public API ──────────────────────────────────────────────────

    def start(self) -> None:
        """截屏并显示选区界面。"""
        self._screenshot = _capture_all_screens()
        if self._screenshot is None or self._screenshot.isNull():
            self.cancelled.emit()
            self.close()
            return

        # 覆盖虚拟桌面全部区域
        self.setGeometry(_virtual_desktop_rect())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    # ── Paint ───────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        if self._screenshot is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 第 1 层：全屏原图（作为背景）
        painter.drawPixmap(self.rect(), self._screenshot)

        if self._current_rect and self._current_rect.width() > 4 and self._current_rect.height() > 4:
            # 第 2 层：选区之外的半透明遮罩
            mask_path = QPainterPath()
            mask_path.addRect(QRectF(self.rect()))
            mask_path.addRect(QRectF(self._current_rect))
            painter.setBrush(QColor(0, 0, 0, 120))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(mask_path)

            # 第 3 层：选区蓝色边框 (Indigo #4F46E5)
            pen = QPen(QColor("#4F46E5"), 2)
            pen.setCosmetic(True)  # 边框不随缩放变化
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._current_rect)

            # 第 4 层：尺寸标签
            self._draw_size_label(painter, self._current_rect)
        else:
            # 无选区 — 整屏半透明遮罩
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        painter.end()

    def _draw_size_label(self, painter: QPainter, rect: QRect) -> None:
        """在选区右下角绘制尺寸标签 (W×H)。"""
        text = f"{rect.width()} × {rect.height()}"
        font = QFont()
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)

        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        text_height = fm.height()
        padding = 6

        # 标签放在选区右下角外侧（若空间不足则放在内侧）
        label_x = rect.right()  - text_width  - padding * 2
        label_y = rect.bottom() - text_height - padding * 2
        if label_x < rect.left():
            label_x = rect.left() + 4
        if label_y < rect.top():
            label_y = rect.top() + 4

        label_rect = QRect(
            label_x - padding,
            label_y - padding,
            text_width  + padding * 2,
            text_height + padding * 2,
        )

        painter.setBrush(QColor(0, 0, 0, 160))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(label_rect, 4, 4)

        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)

    # ── Mouse ───────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._current_rect = QRect(self._origin, self._origin)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._origin is not None:
            self._current_rect = QRect(self._origin, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._origin is not None:
            self._current_rect = QRect(self._origin, event.pos()).normalized()
            if self._current_rect.width() > 8 and self._current_rect.height() > 8:
                # 选区有效 → 确认并关闭
                self._confirmed = True
                self._emit_captured()
            else:
                # 选区太小 → 取消
                self.cancelled.emit()
            self.close()

    # ── Keyboard ────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._current_rect and self._current_rect.width() > 4:
                self._confirmed = True
                self._emit_captured()
            else:
                self.cancelled.emit()
            self.close()
        else:
            super().keyPressEvent(event)

    # ── Helpers ─────────────────────────────────────────────────────

    def _emit_captured(self) -> None:
        """裁剪选区 → numpy RGB → emit captured。"""
        if self._screenshot is None or self._current_rect is None:
            self.cancelled.emit()
            return

        rect = self._current_rect
        cropped = self._screenshot.copy(rect)
        arr = _qpixmap_to_numpy(cropped)
        self.captured.emit(arr)


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

def _virtual_desktop_rect() -> QRect:
    """返回所有屏幕的并集区域。"""
    total = QRect()
    for screen in QApplication.screens():
        total = total.united(screen.geometry())
    return total


def _capture_all_screens() -> QPixmap | None:
    """捕获所有屏幕并合成为一张位图。"""
    total_rect = _virtual_desktop_rect()
    if total_rect.width() <= 0 or total_rect.height() <= 0:
        return None

    combined = QPixmap(total_rect.size())
    combined.fill(Qt.GlobalColor.black)

    painter = QPainter(combined)
    for screen in QApplication.screens():
        pixmap = screen.grabWindow(0)
        offset = screen.geometry().topLeft() - total_rect.topLeft()
        painter.drawPixmap(offset, pixmap)
    painter.end()

    return combined


def _build_crosshair_cursor(size: int = 32) -> QCursor:
    """创建高可见度红色十字光标。

    红色十字 + 黑色轮廓，在明暗背景上均清晰可见，热区在中心。
    """
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = size // 2, size // 2

    # 外层：黑色轮廓
    pen_outer = QPen(QColor(0, 0, 0, 200), 3)
    pen_outer.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen_outer)
    painter.drawLine(cx, 3, cx, size - 3)
    painter.drawLine(3, cy, size - 3, cy)

    # 内层：红色核心 (#EF4444)
    pen_inner = QPen(QColor(239, 68, 68), 2)
    pen_inner.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen_inner)
    painter.drawLine(cx, 3, cx, size - 3)
    painter.drawLine(3, cy, size - 3, cy)

    # 中心 4px 镂空
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.drawRect(cx - 2, cy - 2, 4, 4)

    painter.end()
    return QCursor(pix, cx, cy)


def _qpixmap_to_numpy(pixmap: QPixmap) -> np.ndarray:
    """QPixmap → RGB uint8 numpy 数组（深拷贝）。

    正确处理 QImage 的 32-bit 行对齐填充。
    当 ``width * 3`` 不是 4 的倍数时，QImage 会在每行末尾添加
    1–3 字节填充，直接 reshape 会导致像素错位。
    """
    import ctypes as _ct

    qimage = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
    width, height = qimage.width(), qimage.height()
    bpl = qimage.bytesPerLine()  # 可能 > width * 3（含填充）

    ptr = qimage.constBits()
    ptr.setsize(qimage.sizeInBytes())

    # 通过 ctypes 安全读取 sip.voidptr → numpy
    buf_type = _ct.c_uint8 * qimage.sizeInBytes()
    buf = buf_type.from_address(int(ptr))
    raw = np.ctypeslib.as_array(buf).reshape(height, bpl)

    if bpl == width * 3:
        # 无填充 — 快速路径
        return raw.reshape(height, width, 3).copy()
    # 有填充 — 裁剪掉每行末尾的冗余字节
    return raw[:, :width * 3].reshape(height, width, 3).copy()
