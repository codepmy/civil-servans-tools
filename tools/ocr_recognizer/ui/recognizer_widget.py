"""OCR Text Recognition tool page.

A self-contained PyQt6 widget that provides image text recognition
via PaddleOCR. Supports printed / handwritten mode switching,
confidence-coloured annotations, and TXT export.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from PyQt6.QtCore import QEvent, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from tools.ocr_engine import OCRRegion
from tools.ocr_recognizer.ui.worker import OCRWorker

# ── supported image extensions ────────────────────────────────────────
_IMAGE_FILTER = (
    "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.webp *.gif *.ico);;"
    "所有文件 (*.*)"
)

# Confidence level tag used in the text panel.
_CONF_TAGS = {
    "high": "●",    # ≥ 0.9
    "mid": "◐",     # 0.7 – 0.9
    "low": "○",     # < 0.7
}


# ======================================================================
# Main widget
# ======================================================================


class OCRRecognizerWidget(QWidget):
    """OCR 文字识别工具主页面。"""

    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tool-page")
        self._image_path: str | None = None
        self._display_pixmap: QPixmap | None = None
        self._full_pixmap: QPixmap | None = None  # unscaled original for auto-fit
        self._regions: list[OCRRegion] = []
        self._worker: OCRWorker | None = None
        self._handwritten = False

        self._setup_ui()
        self._update_button_states()

    # ==================================================================
    # UI construction
    # ==================================================================

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 12)
        layout.setSpacing(0)

        layout.addWidget(self._create_top_bar())
        layout.addSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_image_panel())
        splitter.addWidget(self._create_text_panel())
        splitter.setSizes([700, 700])
        layout.addWidget(splitter, stretch=1)

    # ── top bar ───────────────────────────────────────────────────

    def _create_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("ocr-top-bar")
        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(0, 4, 0, 4)
        hbox.setSpacing(8)

        # Back button
        btn_back = QPushButton("←")
        btn_back.setObjectName("btn-back")
        btn_back.clicked.connect(self.back_requested.emit)
        hbox.addWidget(btn_back)

        # Open
        self._btn_open = QPushButton("📂 打开图片")
        self._btn_open.clicked.connect(self._on_open)
        hbox.addWidget(self._btn_open)

        # Recognise
        self._btn_recognise = QPushButton("▶ 开始识别")
        self._btn_recognise.setProperty("cssClass", "primary")
        self._btn_recognise.clicked.connect(self._on_recognise)
        hbox.addWidget(self._btn_recognise)

        hbox.addSpacing(16)

        # Printed / handwritten toggle
        self._radio_printed = QRadioButton("印刷体")
        self._radio_handwritten = QRadioButton("手写体")
        self._radio_printed.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self._radio_printed)
        group.addButton(self._radio_handwritten)
        group.buttonClicked.connect(self._on_mode_changed)
        hbox.addWidget(self._radio_printed)
        hbox.addWidget(self._radio_handwritten)

        hbox.addSpacing(16)

        # Copy
        self._btn_copy = QPushButton("📋 复制")
        self._btn_copy.clicked.connect(self._on_copy)
        hbox.addWidget(self._btn_copy)

        # Export TXT
        self._btn_export = QPushButton("💾 导出 TXT")
        self._btn_export.clicked.connect(self._on_export_txt)
        hbox.addWidget(self._btn_export)

        # Copy context menu action (so Ctrl+C works on image panel)
        self._copy_action = QAction("复制文本", self)
        self._copy_action.setShortcut("Ctrl+C")
        self._copy_action.triggered.connect(self._on_copy)
        self.addAction(self._copy_action)

        hbox.addStretch()
        return bar

    # ── image panel (left) ─────────────────────────────────────────

    def _create_image_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("ocr-image-panel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        header = QLabel("待识别")
        header.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #374151; "
            "padding: 4px 8px;"
        )
        vbox.addWidget(header)

        self._image_label = QLabel("拖放图片到此处，或点击上方「打开图片」")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(
            "color: #9CA3AF; font-size: 14px; border: 2px dashed #E5E7EB; "
            "border-radius: 12px; background: #F9FAFB;"
        )
        self._image_label.setMinimumHeight(200)

        self._image_scroll = QScrollArea()
        self._image_scroll.setWidgetResizable(True)
        self._image_scroll.setWidget(self._image_label)
        self._image_scroll.installEventFilter(self)
        vbox.addWidget(self._image_scroll, stretch=1)

        # Drag-drop
        self._image_label.setAcceptDrops(True)
        panel.setAcceptDrops(True)
        panel.dragEnterEvent = self._drag_enter_event
        panel.dragMoveEvent = self._drag_move_event
        panel.dropEvent = self._drop_event

        return panel

    # ── text panel (right) ─────────────────────────────────────────

    def _create_text_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("ocr-text-panel")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        header = QLabel("识别结果")
        header.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #374151; "
            "padding: 4px 8px;"
        )
        vbox.addWidget(header)

        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setPlaceholderText("识别结果将显示在这里…")
        self._text_edit.setStyleSheet(
            "font-size: 14px; line-height: 1.6;"
        )
        vbox.addWidget(self._text_edit, stretch=1)

        # Allow text selection + copy via Ctrl+C in the text edit
        self._text_edit.setContextMenuPolicy(
            Qt.ContextMenuPolicy.DefaultContextMenu
        )

        return panel

    # ==================================================================
    # Drag & drop
    # ==================================================================

    def _drag_enter_event(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._image_scroll.setStyleSheet(
                "border: 2px dashed #818CF8; border-radius: 12px;"
            )

    def _drag_move_event(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop_event(self, event) -> None:  # type: ignore[no-untyped-def]
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if self._is_image_file(path):
                try:
                    self._load_image(path)
                except Exception as exc:
                    QMessageBox.warning(
                        self, "加载失败",
                        f"无法加载图片文件：\n{exc}",
                    )

    # ==================================================================
    # Image handling
    # ==================================================================

    @staticmethod
    def _is_image_file(path: str) -> bool:
        ext = Path(path).suffix.lower()
        return ext in {
            ".png", ".jpg", ".jpeg", ".bmp",
            ".tiff", ".tif", ".webp", ".gif", ".ico",
        }

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", _IMAGE_FILTER,
        )
        if path:
            self._load_image(path)

    def _load_image(self, path: str) -> None:
        self._image_path = path
        self._regions = []
        self._text_edit.clear()

        try:
            img = Image.open(path)
            img = img.convert("RGB")
        except Exception as exc:
            QMessageBox.warning(
                self, "加载失败", f"无法打开图片文件：\n{exc}"
            )
            return

        # Keep original at reasonable resolution; auto-fit display scaling
        # is handled in _show_pixmap_on_label via viewport sizing.
        img.thumbnail((3840, 3840), Image.LANCZOS)
        arr = np.array(img)
        h, w, _ = arr.shape
        qimg = self._array_to_qpixmap(arr)

        self._full_pixmap = qimg
        self._display_pixmap = qimg
        self._show_pixmap_on_label(qimg)

        self.status_message.emit(
            f"已加载: {path}（{w} × {h}）"
        )
        self._update_button_states()

    def _show_pixmap_on_label(self, pixmap: QPixmap) -> None:
        """Display *pixmap* scaled to fit the current viewport.

        The original unscaled pixmap is kept in ``_full_pixmap`` so it
        can be re-scaled when the window is resized.
        """
        self._image_label.setStyleSheet(
            "border: none; background: transparent;"
        )
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fit_pixmap_to_viewport()

    def _fit_pixmap_to_viewport(self) -> None:
        """Scale ``_full_pixmap`` to fit the scroll area viewport,
        maintaining aspect ratio."""
        if self._full_pixmap is None:
            return
        viewport = self._image_scroll.viewport()
        if viewport is None:
            return
        avail = viewport.size()
        if avail.width() < 4 or avail.height() < 4:
            return
        # Leave a small margin so the image doesn't touch the edges
        target_w = avail.width() - 16
        target_h = avail.height() - 16
        scaled = self._full_pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    # ── event filter: rescale image on resize ──────────────────────

    def eventFilter(self, obj, event) -> bool:  # type: ignore[no-untyped-def]
        if obj is self._image_scroll and event.type() == QEvent.Type.Resize:
            self._fit_pixmap_to_viewport()
        return super().eventFilter(obj, event)

    @staticmethod
    def _array_to_qpixmap(arr: np.ndarray) -> QPixmap:
        """Convert a numpy RGB array to QPixmap via PyQt6 native QImage.

        Uses QImage's raw-data constructor — avoids PIL.ImageQt which
        can segfault with PyQt6 on Windows.
        """
        arr = np.ascontiguousarray(arr)
        h, w, ch = arr.shape
        bytes_per_line = ch * w
        qimage = QImage(
            arr.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
        )
        return QPixmap.fromImage(qimage)

    # ==================================================================
    # OCR
    # ==================================================================

    def _on_recognise(self) -> None:
        if not self._image_path:
            return

        # ── pre-flight: check PaddleOCR is importable ──────────────
        from tools.ocr_engine.paddle_recognizer import PaddleRecognizer

        ok, reason = PaddleRecognizer.is_available()
        if not ok:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("OCR 依赖未安装")
            msg.setText(reason + "\n\n是否立即运行 setup.bat 安装？")
            install_btn = msg.addButton("安装", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(install_btn)
            msg.exec()
            if msg.clickedButton() == install_btn:
                self._run_setup_bat()
            return

        self._btn_recognise.setEnabled(False)
        self._btn_recognise.setText("识别中…")
        self._text_edit.clear()
        self._regions = []

        self._worker = OCRWorker(
            self._image_path, handwritten=self._handwritten
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, percent: int, stage: str) -> None:
        self.status_message.emit(f"OCR: {stage}")

    def _on_succeeded(
        self, regions: list[OCRRegion], annotated: np.ndarray | None
    ) -> None:
        self._regions = regions

        # Update image with annotations
        if annotated is not None:
            qimg = self._array_to_qpixmap(annotated)
            self._display_pixmap = qimg
            self._full_pixmap = qimg
            self._show_pixmap_on_label(qimg)

        # Populate text
        text = _regions_to_text(regions)
        self._text_edit.setPlainText(text)

        self._btn_recognise.setText("▶ 开始识别")
        self._btn_recognise.setEnabled(True)
        self._update_button_states()

        self.status_message.emit(
            f"OCR 完成 — {len(regions)} 个文字区域"
        )

    def _on_failed(self, message: str) -> None:
        self._btn_recognise.setText("▶ 开始识别")
        self._btn_recognise.setEnabled(True)

        if "CUDNN_MISSING" in message:
            self._show_cudnn_dialog(message)
        else:
            QMessageBox.critical(
                self,
                "识别失败",
                f"OCR 识别过程中出现错误：\n\n{message}",
            )

    def _show_cudnn_dialog(self, message: str) -> None:
        """Show cuDNN installation dialog with a clickable download button."""
        CUDNN_URL = "https://developer.nvidia.com/rdp/cudnn-archive"
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("缺少 cuDNN 运行时")
        msg.setText(message.replace("CUDNN_MISSING\n", ""))
        download_btn = msg.addButton("打开 cuDNN 下载页面", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(download_btn)
        msg.exec()
        if msg.clickedButton() == download_btn:
            QDesktopServices.openUrl(QUrl(CUDNN_URL))

    # ==================================================================
    # Mode switching
    # ==================================================================

    def _on_mode_changed(self) -> None:
        self._handwritten = self._radio_handwritten.isChecked()

    # ==================================================================
    # Output actions
    # ==================================================================

    def _on_copy(self) -> None:
        text = self._text_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status_message.emit("已复制到剪贴板")

    def _on_export_txt(self) -> None:
        text = self._text_edit.toPlainText()
        if not text:
            QMessageBox.information(self, "提示", "没有可导出的识别结果。")
            return

        default_name = (
            Path(self._image_path).stem + "_OCR.txt"
            if self._image_path
            else "ocr_result.txt"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "导出文本", default_name,
            "文本文件 (*.txt);;所有文件 (*.*)",
        )
        if not path:
            return

        try:
            Path(path).write_text(text, encoding="utf-8")
            self.status_message.emit(f"已导出: {path}")
        except OSError as exc:
            QMessageBox.critical(
                self, "导出失败", f"无法写入文件：\n{exc}"
            )

    # ==================================================================
    # Helpers
    # ==================================================================

    def _update_button_states(self) -> None:
        has_image = self._image_path is not None
        has_result = bool(self._regions)
        self._btn_recognise.setEnabled(has_image)
        self._btn_copy.setEnabled(has_result)
        self._btn_export.setEnabled(has_result)

    @staticmethod
    def _run_setup_bat() -> None:
        """Open setup.bat in a new terminal window."""
        from app_paths import app_root

        setup_path = app_root() / "setup.bat"
        if not setup_path.is_file():
            QMessageBox.warning(
                None, "未找到安装脚本",
                f"未找到 setup.bat。\n预期位置: {setup_path}\n\n"
                "请手动运行: pip install paddlepaddle paddleocr",
            )
            return

        try:
            os.startfile(str(setup_path))
        except Exception as exc:
            QMessageBox.warning(
                None, "启动失败",
                f"无法启动 setup.bat：\n{exc}\n\n"
                "请手动双击运行项目根目录下的 setup.bat。",
            )


# ======================================================================
# Text assembly
# ======================================================================


def _regions_to_text(regions: list[OCRRegion]) -> str:
    """Join OCR regions into readable plain text.

    Regions are sorted top-to-bottom, left-to-right. A blank line is
    inserted between rows that are vertically separated by more than
    1.5× the median line height.
    """
    if not regions:
        return ""

    sorted_regions = sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0]))

    # Estimate median line height for paragraph detection
    heights = [
        r.bbox[3] - r.bbox[1]
        for r in sorted_regions
        if (r.bbox[3] - r.bbox[1]) > 0
    ]
    median_h = sorted(heights)[len(heights) // 2] if heights else 20

    lines: list[str] = []
    prev_y1 = float("-inf")

    for region in sorted_regions:
        y0 = region.bbox[1]
        gap = y0 - prev_y1 if prev_y1 > float("-inf") else 0

        if gap > median_h * 1.5 and lines:
            lines.append("")  # paragraph break

        tag = _CONF_TAGS["high"]
        if region.confidence < 0.7:
            tag = _CONF_TAGS["low"]
        elif region.confidence < 0.9:
            tag = _CONF_TAGS["mid"]

        lines.append(region.text)
        prev_y1 = region.bbox[3]

    return "\n".join(lines)
