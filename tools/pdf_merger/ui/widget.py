"""PDF文件拼合主界面。"""

from pathlib import Path

import fitz
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QThread
from PyQt6.QtGui import QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from tools.pdf_merger.core.merger import PdfMerger
from ui.dialogs import show_success

# ============================================================
#  Design tokens (Slate + Indigo)
# ============================================================

CARD_STYLE = (
    "QWidget#card {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 10px;"
    "}"
)

PRIMARY_BTN = (
    "QPushButton {"
    "  background-color: #4F46E5;"
    "  color: #FFFFFF;"
    "  border: none;"
    "  border-radius: 8px;"
    "  padding: 8px 20px;"
    "  font-size: 13px;"
    "  font-weight: 600;"
    "  min-height: 34px;"
    "}"
    "QPushButton:hover { background-color: #4338CA; }"
    "QPushButton:pressed { background-color: #3730A3; }"
    "QPushButton:disabled { background-color: #C7D2FE; color: #FFFFFF; }"
)

SECONDARY_BTN = (
    "QPushButton {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #D1D5DB;"
    "  border-radius: 8px;"
    "  padding: 8px 14px;"
    "  color: #374151;"
    "  font-size: 12px;"
    "  font-weight: 500;"
    "  min-height: 30px;"
    "}"
    "QPushButton:hover { background-color: #F9FAFB; border-color: #9CA3AF; }"
    "QPushButton:disabled { color: #D1D5DB; background-color: #F9FAFB; }"
)

ICON_BTN = (
    "QPushButton {"
    "  background-color: #F3F4F6;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 6px;"
    "  padding: 4px 10px;"
    "  color: #374151;"
    "  font-size: 12px;"
    "  min-height: 26px;"
    "}"
    "QPushButton:hover { background-color: #E5E7EB; }"
    "QPushButton:disabled { color: #D1D5DB; }"
)

DRAG_BORDER = (
    "QListWidget {"
    "  border: 2px dashed #4F46E5;"
    "  border-radius: 8px;"
    "  background-color: #EEF2FF;"
    "  padding: 4px;"
    "}"
)

DEFAULT_LIST = (
    "QListWidget {"
    "  border: none;"
    "  background-color: transparent;"
    "  outline: none;"
    "  padding: 2px;"
    "}"
    "QListWidget::item {"
    "  background-color: #F9FAFB;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 8px;"
    "  padding: 8px 12px;"
    "  margin: 2px 0px;"
    "}"
    "QListWidget::item:selected {"
    "  background-color: #EEF2FF;"
    "  border-color: #A5B4FC;"
    "}"
    "QListWidget::item:hover {"
    "  background-color: #F3F4F6;"
    "  border-color: #D1D5DB;"
    "}"
)

PREVIEW_BG = (
    "QScrollArea {"
    "  border: none;"
    "  background-color: #F3F4F6;"
    "  border-radius: 8px;"
    "}"
)

SEPARATOR_LINE = (
    "background-color: #E5E7EB; max-height: 1px; min-height: 1px;"
)

SPIN_STYLE = (
    "QSpinBox {"
    "  font-size: 11px; color: #374151;"
    "  background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 4px;"
    "  padding: 1px 3px; min-width: 44px; max-width: 54px;"
    "  min-height: 20px; max-height: 20px;"
    "}"
    "QSpinBox:focus { border-color: #4F46E5; }"
    "QSpinBox::up-button, QSpinBox::down-button { width: 12px; }"
)


# ============================================================
#  DropListWidget
# ============================================================

class DropListWidget(QListWidget):
    """Support external PDF drops + internal drag reorder."""

    files_added = pyqtSignal(list)
    order_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setStyleSheet(DEFAULT_LIST)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._external_pdf_drag = False

    def dragEnterEvent(self, event: QDragEnterEvent | None):
        if event is None:
            return
        if event.mimeData() and self._has_external_pdf(event.mimeData()):
            self._external_pdf_drag = True
            self.setStyleSheet(DRAG_BORDER)
            event.acceptProposedAction()
        else:
            self._external_pdf_drag = False
            self.setStyleSheet(DEFAULT_LIST)
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent | None):
        if self._external_pdf_drag and event:
            event.acceptProposedAction()
        elif event:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._external_pdf_drag = False
        self.setStyleSheet(DEFAULT_LIST)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent | None):
        self.setStyleSheet(DEFAULT_LIST)
        if self._external_pdf_drag and event and event.mimeData():
            paths = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.isLocalFile()
                and Path(url.toLocalFile()).suffix.lower() == ".pdf"
            ]
            self._external_pdf_drag = False
            if paths:
                self.files_added.emit(paths)
                event.acceptProposedAction()
                return
        self._external_pdf_drag = False
        super().dropEvent(event)
        self.order_changed.emit()

    @staticmethod
    def _has_external_pdf(mime_data) -> bool:
        if not mime_data.hasUrls():
            return False
        return any(
            url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".pdf"
            for url in mime_data.urls()
        )

    def startDrag(self, supportedActions: Qt.DropAction):
        item = self.currentItem()
        if item is None:
            super().startDrag(supportedActions)
            return

        item_widget = self.itemWidget(item)
        if item_widget is not None:
            pixmap = item_widget.grab()
        else:
            rect = self.visualItemRect(item)
            pixmap = self.viewport().grab(rect)

        transparent = QPixmap(pixmap.size())
        transparent.fill(Qt.GlobalColor.transparent)
        painter = QPainter(transparent)
        painter.setOpacity(0.65)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        drag = QDrag(self)
        drag.setPixmap(transparent)
        drag.setHotSpot(QPoint(transparent.width() // 2, transparent.height() // 2))

        mime_data = self.mimeData(self.selectedItems())
        if mime_data is None:
            mime_data = QMimeData()
        drag.setMimeData(mime_data)

        drag.exec(supportedActions)


# ============================================================
#  FileItemWidget -- with page range spinners
# ============================================================

class FileItemWidget(QWidget):
    """File row: index + filename + metadata + page range controls."""

    def __init__(self, index: int, filename: str, page_count: int, file_size: int, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self._index = index
        self._page_count = page_count
        self._name_label: QLabel | None = None
        self._meta_label: QLabel | None = None
        self._index_label: QLabel | None = None
        self._spin_start: QSpinBox | None = None
        self._spin_end: QSpinBox | None = None
        self._setup_ui(filename, page_count, file_size)

    def page_range(self) -> tuple[int, int]:
        """Return (start_page, end_page) 1-indexed."""
        start = self._spin_start.value() if self._spin_start else 1
        end = self._spin_end.value() if self._spin_end else self._page_count
        return (start, end)

    def update_display(self, index: int, filename: str, page_count: int, file_size: int):
        self._index = index
        if self._index_label:
            self._index_label.setText(f"{index:02d}")
        if self._name_label:
            self._name_label.setText(filename)
        if self._meta_label:
            size_mb = file_size / (1024 * 1024)
            if size_mb >= 1.0:
                size_text = f"{size_mb:.1f} MB"
            else:
                size_text = f"{file_size / 1024:.1f} KB"
            self._meta_label.setText(f"{page_count} 页 / {size_text}")

    def _setup_ui(self, filename: str, page_count: int, file_size: int):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # Row 1: index + filename + page range + grip
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._index_label = QLabel(f"{self._index:02d}")
        self._index_label.setFixedWidth(28)
        self._index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._index_label.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #4F46E5;"
            "background: transparent; border: none;"
        )
        row1.addWidget(self._index_label)

        self._name_label = QLabel(filename)
        self._name_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #1F2937;"
            "background: transparent; border: none;"
        )
        row1.addWidget(self._name_label, stretch=1)

        # page range on same row as filename
        lbl_range = QLabel("拼合")
        lbl_range.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent; border: none;"
        )
        row1.addWidget(lbl_range)

        self._spin_start = QSpinBox()
        self._spin_start.setRange(1, page_count)
        self._spin_start.setValue(1)
        self._spin_start.setToolTip(f"起始页 (1-{page_count})")
        self._spin_start.setStyleSheet(SPIN_STYLE)
        self._spin_start.valueChanged.connect(self._on_start_changed)
        row1.addWidget(self._spin_start)

        dash = QLabel("—")
        dash.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent; border: none;"
        )
        row1.addWidget(dash)

        self._spin_end = QSpinBox()
        self._spin_end.setRange(1, page_count)
        self._spin_end.setValue(page_count)
        self._spin_end.setToolTip(f"结束页 (1-{page_count})")
        self._spin_end.setStyleSheet(SPIN_STYLE)
        self._spin_end.valueChanged.connect(self._on_end_changed)
        row1.addWidget(self._spin_end)

        lbl_page = QLabel("页")
        lbl_page.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent; border: none;"
        )
        row1.addWidget(lbl_page)

        grip = QLabel("⋮⋮")
        grip.setFixedWidth(20)
        grip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grip.setStyleSheet(
            "font-size: 14px; color: #D1D5DB; background: transparent; border: none;"
            "letter-spacing: -2px;"
        )
        row1.addWidget(grip)

        layout.addLayout(row1)

        # Row 2: meta info (indented to align with filename)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addSpacing(38)  # align with filename (28px index + 10px gap)

        size_mb = file_size / (1024 * 1024)
        if size_mb >= 1.0:
            size_text = f"{size_mb:.1f} MB"
        else:
            size_text = f"{file_size / 1024:.1f} KB"

        self._meta_label = QLabel(f"{page_count} 页 / {size_text}")
        self._meta_label.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent; border: none;"
        )
        row2.addWidget(self._meta_label)
        row2.addStretch()

        layout.addLayout(row2)

    def _on_start_changed(self, value: int):
        if self._spin_end and value > self._spin_end.value():
            self._spin_end.setValue(value)

    def _on_end_changed(self, value: int):
        if self._spin_start and value < self._spin_start.value():
            self._spin_start.setValue(value)


# ============================================================
#  PdfPreviewPanel
# ============================================================

class PdfPreviewPanel(QWidget):
    """PDF preview with page navigation."""

    def __init__(self):
        super().__init__()
        self._doc: fitz.Document | None = None
        self._current_page: int = 0
        self._pixmap: QPixmap | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title = QLabel("\U0001f4c4 预览")  # 📄 预览
        title.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #111827;"
            "background: transparent; border: none;"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        self.label_file_info = QLabel("")
        self.label_file_info.setStyleSheet(
            "font-size: 12px; color: #9CA3AF; background: transparent; border: none;"
        )
        header_row.addWidget(self.label_file_info)

        layout.addLayout(header_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet(PREVIEW_BG)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.image_label = QLabel("")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("color: #9CA3AF; font-size: 14px; background: transparent;")
        self.scroll_area.setWidget(self.image_label)
        self._show_placeholder_text()
        layout.addWidget(self.scroll_area, stretch=1)

        nav = QHBoxLayout()
        nav.setSpacing(10)

        self.btn_prev = QPushButton("◀ 上一页")  # ◀ 上一页
        self.btn_prev.setStyleSheet(SECONDARY_BTN)
        self.btn_prev.setFixedWidth(100)
        self.btn_prev.clicked.connect(self._prev_page)
        nav.addWidget(self.btn_prev)

        nav.addStretch()

        self.label_page = QLabel("- / -")
        self.label_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_page.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #6B7280;"
            "background: transparent; border: none;"
        )
        nav.addWidget(self.label_page)

        nav.addStretch()

        self.btn_next = QPushButton("下一页 ▶")  # 下一页 ▶
        self.btn_next.setStyleSheet(SECONDARY_BTN)
        self.btn_next.setFixedWidth(100)
        self.btn_next.clicked.connect(self._next_page)
        nav.addWidget(self.btn_next)

        layout.addLayout(nav)
        self._update_nav()

    def _show_placeholder_text(self):
        """在 image_label 上显示占位文字（不切换 scroll widget）。"""
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("在左侧选择文件即可预览")
        self.image_label.setStyleSheet("color: #9CA3AF; font-size: 14px; background: transparent;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull():
            self._fit_to_view()

    def show_file(self, path: str):
        if self._doc:
            self._doc.close()
            self._doc = None
        self._current_page = 0
        self._pixmap = None

        try:
            file_path = Path(path)
            file_size = file_path.stat().st_size

            self._doc = fitz.open(str(file_path))
            if self._doc.page_count == 0:
                self._show_placeholder_text()
                self._update_nav()
                self.label_file_info.setText("0 页")
                return

            self._render_current_page()

            size_mb = file_size / (1024 * 1024)
            if size_mb >= 1.0:
                size_text = f"{size_mb:.1f} MB"
            else:
                size_text = f"{file_size / 1024:.1f} KB"
            self.label_file_info.setText(f"{self._doc.page_count} 页 / {size_text}")

        except Exception:
            self._show_placeholder_text()
            self.label_file_info.setText("加载失败")
            self._doc = None
            self._update_nav()

    def clear(self):
        if self._doc:
            self._doc.close()
            self._doc = None
        self._current_page = 0
        self._pixmap = None
        self._show_placeholder_text()
        self.label_file_info.setText("")
        self._update_nav()

    def _render_current_page(self):
        if not self._doc or self._doc.page_count == 0:
            self._show_placeholder_text()
            return
        self.image_label.setText("")
        self.image_label.setStyleSheet("background: transparent;")
        page = self._doc[self._current_page]
        pix = page.get_pixmap(dpi=150, alpha=False)
        img = QImage(
            pix.samples, pix.width, pix.height,
            pix.stride, QImage.Format.Format_RGB888,
        )
        self._pixmap = QPixmap.fromImage(img)
        self._fit_to_view()
        self._update_nav()

    def _fit_to_view(self):
        if not self._pixmap or self._pixmap.isNull():
            return
        avail_w = max(100, self.scroll_area.viewport().width() - 24)
        avail_h = max(100, self.scroll_area.viewport().height() - 24)
        scaled = self._pixmap.scaled(
            avail_w, avail_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def _update_nav(self):
        has_doc = bool(self._doc and self._doc.page_count)
        total = self._doc.page_count if has_doc else 0
        self.btn_prev.setEnabled(has_doc and self._current_page > 0)
        self.btn_next.setEnabled(has_doc and self._current_page < total - 1)
        if has_doc:
            self.label_page.setText(f"第 {self._current_page + 1} / {total} 页")  # 第 X / N 页
        else:
            self.label_page.setText("- / -")

    def _prev_page(self):
        if self._doc and self._current_page > 0:
            self._current_page -= 1
            self._render_current_page()

    def _next_page(self):
        if self._doc and self._current_page < self._doc.page_count - 1:
            self._current_page += 1
            self._render_current_page()


# ============================================================
#  MergeProgressDialog
# ============================================================

class MergeProgressDialog(QDialog):
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("正在拼合...")  # 正在拼合...
        self.setFixedSize(400, 160)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setStyleSheet("QDialog { background-color: #FFFFFF; border-radius: 10px; }")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        self.label_status = QLabel("准备中...")  # 准备中...
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_status.setStyleSheet(
            "font-size: 13px; color: #374151; font-weight: 500; background: transparent;"
        )
        layout.addWidget(self.label_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.btn_cancel = QPushButton("取消")  # 取消
        self.btn_cancel.setProperty("cssClass", "link")
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignCenter)

    def update_progress(self, percent: int, status: str):
        self.progress_bar.setValue(percent)
        self.label_status.setText(f"{status}")

    def _on_cancel(self):
        self.cancelled.emit()
        self.reject()


# ============================================================
#  MergeWorker
# ============================================================

class MergeWorker(QThread):
    progress = pyqtSignal(int, int, str)
    succeeded = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, paths: list[str], page_ranges: list[tuple[int, int]] | None = None):
        super().__init__()
        self._paths = paths
        self._page_ranges = page_ranges

    def run(self):
        try:
            merger = PdfMerger()
            result = merger.merge(
                self._paths,
                progress_callback=self._on_progress,
                page_ranges=self._page_ranges,
            )
            self.succeeded.emit(result)
        except BaseException as exc:
            import traceback
            detail = traceback.format_exc()
            self.failed.emit(f"{exc}\n\n详细信息:\n{detail[-2000:]}")

    def _on_progress(self, current: int, total: int, filename: str):
        if self.isInterruptionRequested():
            raise RuntimeError("用户已取消拼合。")  # 用户已取消拼合。
        self.progress.emit(current, total, filename)


# ============================================================
#  PdfMergerWidget -- main page
# ============================================================

class PdfMergerWidget(QWidget):
    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._output_bytes: bytes | None = None
        self._worker: MergeWorker | None = None
        self._progress_dialog: MergeProgressDialog | None = None
        self._total_pages = 0
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(14)
        self._build_header(root)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #E5E7EB; margin: 0 6px; }")
        splitter.addWidget(self._build_file_list_card())
        splitter.addWidget(self._build_preview_card())
        splitter.setSizes([420, 740])
        root.addWidget(splitter, stretch=1)
        self._build_footer(root)

    def _build_header(self, root: QVBoxLayout):
        header = QHBoxLayout()
        header.setSpacing(12)

        self.btn_back = QPushButton("←")  # ←
        self.btn_back.setObjectName("btn-back")
        self.btn_back.setToolTip("返回首页")  # 返回首页
        header.addWidget(self.btn_back)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)

        title = QLabel("PDF 文件拼合")  # PDF 文件拼合
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #111827; background: transparent; border: none;")
        title_col.addWidget(title)

        subtitle = QLabel("选择多个 PDF，按顺序合并为一个文件")
        subtitle.setStyleSheet("font-size: 12px; color: #9CA3AF; background: transparent; border: none;")
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()
        root.addLayout(header)

    def _build_file_list_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        card_title = QLabel("\U0001f4c2 文件列表")  # 📂 文件列表
        card_title.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #111827; background: transparent; border: none;"
        )
        title_row.addWidget(card_title)
        title_row.addStretch()

        self._count_badge = QLabel("")
        self._count_badge.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #4F46E5;"
            "background-color: #EEF2FF; border-radius: 10px; padding: 2px 10px;"
        )
        self._count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_badge.setVisible(False)
        title_row.addWidget(self._count_badge)
        card_layout.addLayout(title_row)

        self._drop_hint = QLabel("拖拽 PDF 文件到此处，或点击下方按钮添加")
        self._drop_hint.setStyleSheet("font-size: 12px; color: #9CA3AF; background: transparent; border: none;")
        self._drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self._drop_hint)

        self.list_widget = DropListWidget()
        self.list_widget.files_added.connect(self._add_paths)
        self.list_widget.order_changed.connect(self._on_order_changed)
        card_layout.addWidget(self.list_widget, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_up = QPushButton("▲ 上移")  # ▲ 上移
        self.btn_up.setStyleSheet(ICON_BTN)
        self.btn_up.setEnabled(False)
        btn_row.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼ 下移")  # ▼ 下移
        self.btn_down.setStyleSheet(ICON_BTN)
        self.btn_down.setEnabled(False)
        btn_row.addWidget(self.btn_down)

        btn_row.addStretch()

        self.btn_remove = QPushButton("✕ 移除")  # ✕ 移除
        self.btn_remove.setStyleSheet(
            ICON_BTN.replace("#374151", "#DC2626").replace("#E5E7EB", "#FECACA")
            + "QPushButton:hover { background-color: #FEF2F2; border-color: #FCA5A5; color: #B91C1C; }"
        )
        self.btn_remove.setEnabled(False)
        btn_row.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("清空")

        self.btn_clear.setStyleSheet(
            "QPushButton {"
            "  background-color: #FEF2F2; color: #DC2626;"
            "  border: 1px solid #FECACA; border-radius: 6px;"
            "  padding: 4px 10px; font-size: 12px; font-weight: 600;"
            "  min-height: 26px;"
            "}"
            "QPushButton:hover { background-color: #FEE2E2; border-color: #FCA5A5; }"
            "QPushButton:disabled { background-color: #F9FAFB; color: #D1D5DB; border-color: #E5E7EB; }"
        )
        self.btn_clear.setEnabled(False)
        btn_row.addWidget(self.btn_clear)

        self.btn_add = QPushButton("＋ 添加文件")
        self.btn_add.setStyleSheet(
            "QPushButton {"
            "  background-color: #4F46E5; color: #FFFFFF; border: none;"
            "  border-radius: 6px; padding: 4px 10px;"
            "  font-size: 12px; font-weight: 600; min-height: 26px;"
            "}"
            "QPushButton:hover { background-color: #4338CA; }"
            "QPushButton:disabled { background-color: #C7D2FE; color: #FFFFFF; }"
        )
        btn_row.addWidget(self.btn_add)

        card_layout.addLayout(btn_row)
        return card

    def _build_preview_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(0)
        self.preview = PdfPreviewPanel()
        card_layout.addWidget(self.preview, stretch=1)
        return card

    def _build_footer(self, root: QVBoxLayout):
        footer = QVBoxLayout()
        footer.setSpacing(10)

        sep = QFrame()
        sep.setStyleSheet(SEPARATOR_LINE)
        sep.setFrameShape(QFrame.Shape.HLine)
        footer.addWidget(sep)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.label_summary = QLabel("添加 PDF 文件即可开始拼合")  # 添加 PDF 文件即可开始拼合
        self.label_summary.setStyleSheet("font-size: 13px; color: #6B7280; background: transparent; border: none;")
        action_row.addWidget(self.label_summary, stretch=1)

        self.btn_merge = QPushButton("▶ 开始拼合")  # ▶ 开始拼合
        self.btn_merge.setStyleSheet(PRIMARY_BTN)
        self.btn_merge.setEnabled(False)
        action_row.addWidget(self.btn_merge)

        self.btn_save = QPushButton("\U0001f4be 保存结果")  # 💾 保存结果
        self.btn_save.setStyleSheet(SECONDARY_BTN)
        self.btn_save.setEnabled(False)
        action_row.addWidget(self.btn_save)

        footer.addLayout(action_row)
        root.addLayout(footer)

    # -- signals -------------------------------------------------

    def _connect_signals(self):
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)
        self.btn_add.clicked.connect(self._on_add_files)
        self.btn_remove.clicked.connect(self._on_remove_selected)
        self.btn_clear.clicked.connect(self._on_clear_all)
        self.btn_merge.clicked.connect(self._on_merge)
        self.btn_save.clicked.connect(self._on_save)

    # -- file list ops ------------------------------------------

    def _add_paths(self, paths: list[str]):
        existing = {
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        }
        added = 0
        for p in paths:
            if p in existing:
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(p)
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint()))

            try:
                doc = fitz.open(p)
                page_count = doc.page_count
                doc.close()
            except Exception:
                page_count = 0
            try:
                file_size = Path(p).stat().st_size
            except Exception:
                file_size = 0

            widget = FileItemWidget(
                self.list_widget.count() + 1,
                Path(p).name,
                page_count,
                file_size,
            )
            item.setData(Qt.ItemDataRole.UserRole + 1, widget)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

            existing.add(p)
            added += 1
        if added:
            self._update_summary()

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择PDF文件", "", "PDF文件 (*.pdf);;所有文件 (*.*)"
        )
        if paths:
            self._add_paths(paths)

    def _on_remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self._renumber_items()
        self._update_summary()

    def _on_clear_all(self):
        self.list_widget.clear()
        self.preview.clear()
        self._update_summary()

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row <= 0:
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(row - 1, item)
        self.list_widget.setCurrentRow(row - 1)
        self._renumber_items()
        self._update_summary()

    def _move_down(self):
        row = self.list_widget.currentRow()
        if row >= self.list_widget.count() - 1:
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(row + 1, item)
        self.list_widget.setCurrentRow(row + 1)
        self._renumber_items()
        self._update_summary()

    def _on_order_changed(self):
        self._renumber_items()
        self._update_summary()

    def _renumber_items(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = item.data(Qt.ItemDataRole.UserRole + 1)
            if isinstance(widget, FileItemWidget):
                widget._index = i + 1
                if widget._index_label:
                    widget._index_label.setText(f"{i + 1:02d}")

    def _on_selection_changed(self):
        selected = self.list_widget.selectedItems()
        has_selection = len(selected) > 0
        self.btn_remove.setEnabled(has_selection)

        row = self.list_widget.currentRow()
        self.btn_up.setEnabled(has_selection and row > 0)
        self.btn_down.setEnabled(has_selection and row < self.list_widget.count() - 1)

        if has_selection:
            path = selected[0].data(Qt.ItemDataRole.UserRole)
            self.preview.show_file(path)
        else:
            self.preview.clear()

    # -- data access --------------------------------------------

    def _paths(self) -> list[str]:
        return [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        ]

    def _page_ranges(self) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        for i in range(self.list_widget.count()):
            widget = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole + 1)
            if isinstance(widget, FileItemWidget):
                ranges.append(widget.page_range())
            else:
                ranges.append((1, 9999))
        return ranges

    def _update_summary(self):
        count = self.list_widget.count()
        has_files = count > 0
        self.btn_merge.setEnabled(has_files)
        self.btn_clear.setEnabled(has_files)
        self._output_bytes = None
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet(SECONDARY_BTN)

        self._drop_hint.setVisible(not has_files)

        if has_files:
            self._count_badge.setText(f"{count} 个文件")  # N 个文件
            self._count_badge.setVisible(True)
        else:
            self._count_badge.setVisible(False)

        if not has_files:
            self.label_summary.setText("添加 PDF 文件即可开始拼合")
            self.label_summary.setStyleSheet("font-size: 13px; color: #6B7280; background: transparent; border: none;")
            self.status_message.emit("PDF文件拼合 - 请添加文件开始")
            return

        # Count pages according to selected ranges
        self._total_pages = 0
        failed = 0
        for i in range(self.list_widget.count()):
            path = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            widget = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole + 1)
            try:
                doc = fitz.open(path)
                full_pages = doc.page_count
                doc.close()
                if isinstance(widget, FileItemWidget):
                    start, end = widget.page_range()
                    selected = max(0, min(end, full_pages) - max(1, start) + 1)
                    self._total_pages += selected
                else:
                    self._total_pages += full_pages
            except Exception:
                failed += 1

        parts = [f"共 {count} 个文件"]
        if self._total_pages > 0:
            parts.append(f"预计合并后 {self._total_pages} 页")
        if failed:
            parts.append(f"（{failed} 个无法读取）")

        summary = " · ".join(parts)
        self.label_summary.setText(summary)
        self.label_summary.setStyleSheet("font-size: 13px; color: #6B7280; background: transparent; border: none;")
        self.status_message.emit(f"PDF文件拼合 - {summary}")

    # -- merge ops ----------------------------------------------

    def _on_merge(self):
        paths = self._paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先添加PDF文件。")
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在拼合中，请稍候。")
            return

        self._output_bytes = None
        self.btn_merge.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet(SECONDARY_BTN)

        self._progress_dialog = MergeProgressDialog(self)
        self._progress_dialog.show()

        page_ranges = self._page_ranges()
        self._worker = MergeWorker(paths, page_ranges)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_merge_done)
        self._worker.failed.connect(self._on_merge_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._progress_dialog.cancelled.connect(self._on_cancel_merge)
        self._worker.start()

    def _on_progress(self, current: int, total: int, filename: str):
        if self._progress_dialog:
            pct = int(current / max(total, 1) * 100)
            self._progress_dialog.update_progress(
                pct, f"正在拼合… {current}/{total}  —  {filename}"
            )

    def _on_merge_done(self, pdf_bytes: bytes):
        self._close_progress_dialog()
        self._output_bytes = pdf_bytes

        size_kb = len(pdf_bytes) / 1024
        size_mb = size_kb / 1024
        if size_mb >= 1.0:
            size_text = f"{size_mb:.1f} MB"
        else:
            size_text = f"{size_kb:.1f} KB"

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages = doc.page_count
            doc.close()
        except Exception:
            pages = 0

        summary = f"✅ 拼合完成！共 {pages} 页，{size_text} — 请点击「\U0001f4be 保存结果」保存文件"
        self.label_summary.setText(summary)
        self.label_summary.setStyleSheet("font-size: 14px; font-weight: 600; color: #059669; background: transparent; border: none;")
        self.status_message.emit(f"PDF文件拼合 - 拼合完成，共 {pages} 页，{size_text}")
        self.btn_merge.setEnabled(True)
        self.btn_save.setStyleSheet(PRIMARY_BTN)
        self.btn_save.setEnabled(True)

        show_success(
            self,
            "拼合完成",
            f"PDF 拼合成功！共 {pages} 页 · {size_text}\n"
            f"请点击右下角「\U0001f4be 保存结果」按钮将文件保存到本地。",
        )

    def _on_merge_error(self, error_msg: str):
        self._close_progress_dialog()
        QMessageBox.critical(self, "拼合失败", f"拼合过程中出现错误:\n\n{error_msg}")
        self.label_summary.setText("拼合失败，请重试")
        self.label_summary.setStyleSheet("font-size: 13px; color: #DC2626; font-weight: 500; background: transparent; border: none;")
        self.status_message.emit("PDF文件拼合 - 失败")
        self.btn_merge.setEnabled(True)

    def _on_worker_finished(self):
        if self._worker:
            self._worker.deleteLater()
        self._worker = None

    def _on_cancel_merge(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self.label_summary.setText("已取消拼合")
            self.label_summary.setStyleSheet("font-size: 13px; color: #6B7280; background: transparent; border: none;")
            self.status_message.emit("PDF文件拼合 - 已取消")

    def _close_progress_dialog(self):
        if self._progress_dialog:
            try:
                self._progress_dialog.accept()
            except Exception:
                pass
            self._progress_dialog = None

    # -- save ---------------------------------------------------

    def _on_save(self):
        if not self._output_bytes:
            QMessageBox.information(self, "提示", "请先执行拼合。")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "保存拼合后的PDF", "拼合后.pdf", "PDF文件 (*.pdf)"
        )
        if not path:
            return

        try:
            with open(path, "wb") as f:
                f.write(self._output_bytes)
            self.label_summary.setText(f"已保存：{path}")
            self.label_summary.setStyleSheet("font-size: 13px; color: #059669; font-weight: 500; background: transparent; border: none;")
            self.status_message.emit(f"PDF文件拼合 - 已保存到 {path}")
            show_success(self, "保存成功", f"PDF 已保存到：\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            self.status_message.emit("PDF文件拼合 - 保存失败")
