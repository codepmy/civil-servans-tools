"""双栏PDF预览面板: 左侧显示原始PDF，右侧显示转换后PDF。
预览图片自适应面板宽度，无需手动缩放。"""

import fitz
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QScrollArea, QPushButton, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage


class PDFPreviewWidget(QWidget):
    """单个PDF预览组件: 显示一个PDF的页面，支持翻页，自适应宽度。"""

    page_changed = pyqtSignal(int)

    def __init__(self, title: str = "预览"):
        super().__init__()
        self._doc = None
        self._current_page = 0
        self._title = title
        self._cached_pixmap: QPixmap | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # 标题
        self.label_title = QLabel(self._title)
        self.label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_title.setStyleSheet(
            "font-weight: 600; font-size: 13px; color: #374151; "
            "padding: 6px 8px; background-color: #FFFFFF; "
            "border-bottom: 1px solid #E5E7EB;"
        )
        layout.addWidget(self.label_title)

        # 预览图片 (scroll area)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: 1px solid #E5E7EB; "
            "border-radius: 4px; background-color: #F3F4F6; }"
        )

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setText("请打开PDF文件")
        self.image_label.setStyleSheet("color: #9CA3AF; font-size: 14px; background: transparent;")
        self.image_label.setScaledContents(False)
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area, stretch=1)

        # 翻页控制（含页数跳转）
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(4)
        nav_layout.setContentsMargins(0, 4, 0, 0)

        self.btn_prev = QPushButton("◀ 上一页")
        self.btn_prev.setEnabled(False)
        self.btn_prev.setStyleSheet(
            "QPushButton { padding: 4px 12px; font-size: 12px; }"
        )
        self.btn_prev.clicked.connect(self._prev_page)

        nav_layout.addWidget(self.btn_prev)
        nav_layout.addStretch()

        self.label_jump_prefix = QLabel("第")
        self.label_jump_prefix.setStyleSheet("color: #6B7280; font-size: 12px; background: transparent;")
        nav_layout.addWidget(self.label_jump_prefix)

        self.input_jump_page = QLineEdit()
        self.input_jump_page.setFixedWidth(44)
        self.input_jump_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_jump_page.setStyleSheet(
            "QLineEdit { border: 1px solid #D1D5DB; border-radius: 3px; "
            "padding: 2px 4px; font-size: 12px; background: #FFFFFF; }"
        )
        self.input_jump_page.returnPressed.connect(self._jump_to_page)
        nav_layout.addWidget(self.input_jump_page)

        self.label_page = QLabel(" / — 页")
        self.label_page.setStyleSheet("color: #6B7280; font-size: 12px;")
        nav_layout.addWidget(self.label_page)

        nav_layout.addStretch()
        self.btn_next = QPushButton("下一页 ▶")
        self.btn_next.setEnabled(False)
        self.btn_next.setStyleSheet(
            "QPushButton { padding: 4px 12px; font-size: 12px; }"
        )
        self.btn_next.clicked.connect(self._next_page)
        nav_layout.addWidget(self.btn_next)

        layout.addLayout(nav_layout)

    def resizeEvent(self, event):
        """窗口大小变化时重新缩放预览图片。"""
        super().resizeEvent(event)
        if self._cached_pixmap:
            self._fit_to_width()

    def load_pdf(self, path: str):
        """加载PDF文件。"""
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(path)
            self._current_page = 0
            self._render_current_page()
            self._update_nav()
        except Exception as e:
            self.image_label.setText(f"无法加载PDF:\n{e}")

    def load_pdf_bytes(self, pdf_bytes: bytes):
        """从内存加载PDF。"""
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            self._current_page = 0
            self._render_current_page()
            self._update_nav()
        except Exception as e:
            self.image_label.setText(f"预览加载失败\n(可保存后查看)")

    def _render_current_page(self):
        """渲染当前页为高分辨率图片，然后缩放到适配宽度。"""
        if not self._doc or self._current_page >= self._doc.page_count:
            return

        page = self._doc[self._current_page]
        # 用较高 DPI 渲染，保证清晰度
        pix = page.get_pixmap(dpi=200)
        img = QImage(pix.samples, pix.width, pix.height,
                     pix.stride, QImage.Format.Format_RGB888)
        self._cached_pixmap = QPixmap.fromImage(img)
        self._fit_to_width()
        self.label_page.setText(
            f" / {self._doc.page_count} 页"
        )
        self.input_jump_page.setText(str(self._current_page + 1))

    def _fit_to_width(self):
        """将缓存的原始图片缩放到适配当前面板宽度。"""
        if not self._cached_pixmap or self._cached_pixmap.isNull():
            return

        # 可用宽度：scroll_area 宽度减去滚动条和边距
        avail_width = self.scroll_area.viewport().width() - 8
        if avail_width < 50:
            return

        orig_size = self._cached_pixmap.size()
        scale = avail_width / orig_size.width()
        new_w = int(orig_size.width() * scale)
        new_h = int(orig_size.height() * scale)

        scaled = self._cached_pixmap.scaled(
            new_w, new_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def _update_nav(self):
        if not self._doc:
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            return
        self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < self._doc.page_count - 1)

    def _prev_page(self):
        if self._doc and self._current_page > 0:
            self._current_page -= 1
            self._render_current_page()
            self._update_nav()
            self.page_changed.emit(self._current_page)

    def _next_page(self):
        if self._doc and self._current_page < self._doc.page_count - 1:
            self._current_page += 1
            self._render_current_page()
            self._update_nav()
            self.page_changed.emit(self._current_page)

    def _jump_to_page(self):
        """跳转到用户输入的页码。"""
        if not self._doc:
            return
        try:
            page_num = int(self.input_jump_page.text().strip())
            if 1 <= page_num <= self._doc.page_count:
                self._current_page = page_num - 1
                self._render_current_page()
                self._update_nav()
                self.page_changed.emit(self._current_page)
        except ValueError:
            pass

    def clear(self):
        if self._doc:
            self._doc.close()
            self._doc = None
        self._current_page = 0
        self._cached_pixmap = None
        self.image_label.setText("请打开PDF文件")
        self.image_label.setPixmap(QPixmap())
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.input_jump_page.clear()
        self.label_page.setText(" / — 页")


class PreviewPanel(QWidget):
    """双栏预览面板: 左右对比原始PDF和转换后PDF。"""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.input_preview = PDFPreviewWidget("📄 原始PDF")
        self.output_preview = PDFPreviewWidget("📝 转换后预览")

        splitter.addWidget(self.input_preview)
        splitter.addWidget(self.output_preview)
        splitter.setSizes([500, 500])

        layout.addWidget(splitter)

    def load_input(self, path: str):
        self.input_preview.load_pdf(path)

    def load_output(self, pdf_bytes: bytes):
        self.output_preview.load_pdf_bytes(pdf_bytes)

    def clear_all(self):
        self.input_preview.clear()
        self.output_preview.clear()
