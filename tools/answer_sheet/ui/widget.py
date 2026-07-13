from __future__ import annotations

from pathlib import Path

import fitz
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from tools.answer_sheet.core.generator import (
    AnswerSheetConfig,
    AnswerSheetGenerator,
    AnswerSheetQuestion,
    DEFAULT_GRID_LINE_COLOR,
    DEFAULT_GRID_LINE_WIDTH,
)


class AnswerSheetPreview(QWidget):
    """单栏 PDF 预览，展示当前生成的答题纸。"""

    def __init__(self):
        super().__init__()
        self._doc: fitz.Document | None = None
        self._current_page = 0
        self._cached_pixmap: QPixmap | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("答题纸预览")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #111827; "
            "padding: 8px; background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 6px;"
        )
        layout.addWidget(title)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: 1px solid #E5E7EB; border-radius: 6px; background: #F3F4F6; }"
        )
        self.image_label = QLabel("正在生成预览...")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("color: #9CA3AF; font-size: 14px; background: transparent;")
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area, stretch=1)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.btn_prev = QPushButton("< 上一页")
        self.btn_next = QPushButton("下一页 >")
        self.label_page = QLabel("- / -")
        self.label_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_page.setStyleSheet("color: #6B7280; font-size: 12px;")
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_next.clicked.connect(self._next_page)
        nav.addWidget(self.btn_prev)
        nav.addStretch()
        nav.addWidget(self.label_page)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        layout.addLayout(nav)
        self._update_nav()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._cached_pixmap:
            self._fit_to_view()

    def load_pdf_bytes(self, pdf_bytes: bytes):
        if self._doc:
            self._doc.close()
        self._doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self._current_page = min(self._current_page, max(0, self._doc.page_count - 1))
        self._render_current_page()
        self._update_nav()

    def _render_current_page(self):
        if not self._doc or self._doc.page_count == 0:
            return
        page = self._doc[self._current_page]
        pix = page.get_pixmap(dpi=180, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        self._cached_pixmap = QPixmap.fromImage(img)
        self._fit_to_view()
        self.label_page.setText(f"第 {self._current_page + 1} / {self._doc.page_count} 页")

    def _fit_to_view(self):
        if not self._cached_pixmap or self._cached_pixmap.isNull():
            return
        avail_w = max(100, self.scroll_area.viewport().width() - 18)
        avail_h = max(100, self.scroll_area.viewport().height() - 18)
        scaled = self._cached_pixmap.scaled(
            avail_w,
            avail_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def _update_nav(self):
        has_doc = bool(self._doc and self._doc.page_count)
        self.btn_prev.setEnabled(has_doc and self._current_page > 0)
        self.btn_next.setEnabled(has_doc and self._current_page < self._doc.page_count - 1)
        if not has_doc:
            self.label_page.setText("- / -")

    def _prev_page(self):
        if self._doc and self._current_page > 0:
            self._current_page -= 1
            self._render_current_page()
            self._update_nav()

    def _next_page(self):
        if self._doc and self._current_page < self._doc.page_count - 1:
            self._current_page += 1
            self._render_current_page()
            self._update_nav()


class QuestionRow(QFrame):
    """分题模式的一行配置。"""

    remove_requested = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, index: int, title: str, word_count: int):
        super().__init__()
        self.setStyleSheet(
            "QFrame { background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; }"
            "QLabel, QLineEdit, QSpinBox, QPushButton { border: none; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.index_label = QLabel(self._index_text(index))
        self.index_label.setFixedWidth(42)
        self.index_label.setStyleSheet("font-weight: 700; color: #4F46E5; background: transparent;")
        layout.addWidget(self.index_label)

        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("题目名称")
        self.title_edit.setMinimumWidth(90)
        self.title_edit.setStyleSheet(
            "QLineEdit { background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 5px; padding: 5px 8px; }"
            "QLineEdit:focus { border-color: #4F46E5; }"
        )
        layout.addWidget(self.title_edit, stretch=1)

        self.word_spin = QSpinBox()
        self.word_spin.setRange(1, 10000)
        self.word_spin.setValue(word_count)
        self.word_spin.setSuffix(" 字")
        self.word_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.word_spin.setStyleSheet(
            "QSpinBox { background: #FFFFFF; border: 1px solid #D1D5DB; "
            "border-radius: 5px; padding: 5px 8px; }"
            "QSpinBox:focus { border-color: #4F46E5; }"
        )
        self.word_spin.setFixedWidth(96)
        layout.addWidget(self.word_spin)

        self.btn_remove = QPushButton("删除")
        self.btn_remove.setFixedWidth(52)
        self.btn_remove.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 5px; padding: 4px; color: #6B7280; }"
            "QPushButton:hover { color: #B91C1C; background: #FEF2F2; border-color: #FECACA; }"
        )
        layout.addWidget(self.btn_remove)

        self.title_edit.textChanged.connect(self.changed.emit)
        self.word_spin.valueChanged.connect(self.changed.emit)
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self))

    def set_index(self, index: int):
        self.index_label.setText(self._index_text(index))

    def _index_text(self, index: int) -> str:
        return f"第{index}题"

    def question(self, fallback_index: int) -> AnswerSheetQuestion:
        title = self.title_edit.text().strip() or f"第{fallback_index}题"
        return AnswerSheetQuestion(title=title, word_count=self.word_spin.value())


class AnswerSheetWidget(QWidget):
    """申论答题纸生成器主页面。"""

    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, fonts: list[str], generator: AnswerSheetGenerator):
        super().__init__()
        self._fonts = fonts or ["SimSun"]
        self._generator = generator
        self._question_rows: list[QuestionRow] = []
        self._pdf_bytes: bytes | None = None
        self._grid_line_color = DEFAULT_GRID_LINE_COLOR
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(180)
        self._refresh_timer.timeout.connect(self.refresh_preview)

        self._setup_ui()
        self._connect_signals()
        self._add_question("第1题", 300)
        self.radio_standard.setChecked(True)
        self._apply_mode()
        self.refresh_preview()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(12, 8, 12, 8)
        top.setSpacing(8)
        self.btn_back = QPushButton("<")
        self.btn_back.setToolTip("返回首页")
        self.btn_back.setFixedSize(40, 32)
        self.btn_back.setStyleSheet(
            "QPushButton { background-color: #F3F4F6; border: 1px solid #E5E7EB; "
            "border-radius: 17px; font-weight: 600; font-size: 16px; color: #374151; }"
            "QPushButton:hover { background-color: #E5E7EB; border-color: #D1D5DB; }"
        )
        top.addWidget(self.btn_back)
        title = QLabel("申论答题纸生成器")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #111827;")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.preview = AnswerSheetPreview()
        self.settings_panel = self._build_settings_panel()
        self.settings_panel.setMinimumWidth(320)
        self.settings_panel.setMaximumWidth(420)
        splitter.addWidget(self.preview)
        splitter.addWidget(self.settings_panel)
        splitter.setSizes([980, 360])
        root.addWidget(splitter, stretch=1)

    def _build_settings_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: #FFFFFF; border-left: 1px solid #E5E7EB;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        mode_box = QGroupBox("生成模式")
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.setSpacing(8)
        self.mode_group = QButtonGroup(self)
        self.radio_standard = QRadioButton("标准模式：按页数生成")
        self.radio_questions = QRadioButton("分题模式：按题连续排版")
        self.mode_group.addButton(self.radio_standard, 0)
        self.mode_group.addButton(self.radio_questions, 1)
        mode_layout.addWidget(self.radio_standard)
        mode_layout.addWidget(self.radio_questions)
        layout.addWidget(mode_box)

        standard_box = QGroupBox("标准模式设置")
        standard_layout = QVBoxLayout(standard_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("页数"))
        row.addStretch()
        self.spin_pages = QSpinBox()
        self.spin_pages.setRange(1, 100)
        self.spin_pages.setValue(1)
        self.spin_pages.setSuffix(" 页")
        self.spin_pages.setFixedWidth(112)
        row.addWidget(self.spin_pages)
        standard_layout.addLayout(row)
        self.standard_box = standard_box
        layout.addWidget(standard_box)

        question_box = QGroupBox("分题设置")
        question_layout = QVBoxLayout(question_box)
        question_layout.setSpacing(8)
        self.question_container = QWidget()
        self.question_layout = QVBoxLayout(self.question_container)
        self.question_layout.setContentsMargins(0, 0, 0, 0)
        self.question_layout.setSpacing(6)
        self.question_layout.addStretch()

        self.question_scroll = QScrollArea()
        self.question_scroll.setWidgetResizable(True)
        self.question_scroll.setMinimumHeight(180)
        self.question_scroll.setWidget(self.question_container)
        question_layout.addWidget(self.question_scroll)

        self.btn_add_question = QPushButton("+ 添加题目")
        self.btn_add_question.setProperty("cssClass", "primary")
        self.btn_add_question.setMinimumHeight(34)
        self.btn_add_question.setStyleSheet(
            "QPushButton { background: #EEF2FF; border: 1px solid #C7D2FE; border-radius: 6px; "
            "padding: 7px 10px; color: #3730A3; font-weight: 700; }"
            "QPushButton:hover { background: #E0E7FF; border-color: #A5B4FC; }"
        )
        question_layout.addWidget(self.btn_add_question)
        self.question_box = question_box
        layout.addWidget(question_box, stretch=1)

        style_box = QGroupBox("导出设置")
        style_layout = QVBoxLayout(style_box)
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("字体"))
        self.combo_font = QComboBox()
        self.combo_font.addItems(self._fonts)
        if "SimSun" in self._fonts:
            self.combo_font.setCurrentText("SimSun")
        font_row.addWidget(self.combo_font, stretch=1)
        style_layout.addLayout(font_row)

        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("格线粗细"))
        self.slider_line_width = QSlider(Qt.Orientation.Horizontal)
        self.slider_line_width.setRange(10, 200)
        self.slider_line_width.setSingleStep(5)
        self.slider_line_width.setPageStep(10)
        self.slider_line_width.setValue(int(DEFAULT_GRID_LINE_WIDTH * 100))
        self.label_line_width = QLabel(f"{DEFAULT_GRID_LINE_WIDTH:.2f} pt")
        self.label_line_width.setFixedWidth(52)
        self.label_line_width.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        width_row.addWidget(self.slider_line_width, stretch=1)
        width_row.addWidget(self.label_line_width)
        style_layout.addLayout(width_row)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("线条颜色"))
        self.color_swatch = QLabel()
        self.color_swatch.setFixedSize(28, 18)
        self.btn_line_color = QPushButton(DEFAULT_GRID_LINE_COLOR)
        self.btn_line_color.setMinimumHeight(30)
        self.btn_line_color.setFixedWidth(118)
        color_row.addStretch()
        color_row.addWidget(self.color_swatch)
        color_row.addWidget(self.btn_line_color)
        style_layout.addLayout(color_row)
        self._update_color_controls()
        layout.addWidget(style_box)

        layout.addStretch(1)

        actions = QVBoxLayout()
        actions.setSpacing(8)
        self.btn_export_pdf = QPushButton("导出 PDF")
        self.btn_export_pdf.setProperty("cssClass", "primary")
        self.btn_export_image = QPushButton("导出图片")
        self.btn_export_pdf.setMinimumHeight(40)
        self.btn_export_image.setMinimumHeight(36)
        self.btn_export_pdf.setStyleSheet(
            "QPushButton { background: #2563EB; border: 1px solid #1D4ED8; border-radius: 6px; "
            "padding: 9px 12px; color: #FFFFFF; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #1D4ED8; }"
        )
        self.btn_export_image.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 6px; "
            "padding: 8px 12px; color: #374151; font-weight: 600; }"
            "QPushButton:hover { background: #F9FAFB; border-color: #9CA3AF; }"
        )
        actions.addWidget(self.btn_export_pdf)
        actions.addWidget(self.btn_export_image)
        layout.addLayout(actions)

        return panel

    def _connect_signals(self):
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.mode_group.idToggled.connect(lambda _id, checked: checked and self._on_changed())
        self.spin_pages.valueChanged.connect(self._on_changed)
        self.combo_font.currentTextChanged.connect(self._on_changed)
        self.slider_line_width.valueChanged.connect(self._on_line_width_changed)
        self.btn_line_color.clicked.connect(self._choose_line_color)
        self.btn_add_question.clicked.connect(self._on_add_question)
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        self.btn_export_image.clicked.connect(self.export_images)

    def _on_changed(self):
        self._apply_mode()
        self._refresh_timer.start()

    def _apply_mode(self):
        standard = self.radio_standard.isChecked()
        self.standard_box.setVisible(standard)
        self.question_box.setVisible(not standard)

    def _on_add_question(self):
        index = len(self._question_rows) + 1
        self._add_question(f"第{index}题", 300)
        self._on_changed()

    def _add_question(self, title: str, word_count: int):
        row = QuestionRow(len(self._question_rows) + 1, title, word_count)
        row.changed.connect(self._on_changed)
        row.remove_requested.connect(self._remove_question)
        self._question_rows.append(row)
        self.question_layout.insertWidget(self.question_layout.count() - 1, row)
        self._renumber_question_rows()

    def _remove_question(self, row: QuestionRow):
        if len(self._question_rows) <= 1:
            QMessageBox.information(self, "提示", "分题模式至少保留一道题。")
            return
        self._question_rows.remove(row)
        self.question_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._renumber_question_rows()
        self._on_changed()

    def _renumber_question_rows(self):
        for index, row in enumerate(self._question_rows, start=1):
            row.set_index(index)
            row.btn_remove.setEnabled(len(self._question_rows) > 1)

    def _current_config(self) -> AnswerSheetConfig:
        if self.radio_questions.isChecked():
            questions = tuple(
                row.question(index)
                for index, row in enumerate(self._question_rows, start=1)
            )
            return AnswerSheetConfig(
                mode="questions",
                questions=questions,
                font_name=self.combo_font.currentText(),
                grid_line_width=self._current_line_width(),
                grid_line_color=self._grid_line_color,
            )
        return AnswerSheetConfig(
            mode="standard",
            page_count=self.spin_pages.value(),
            title="申论答题纸",
            font_name=self.combo_font.currentText(),
            grid_line_width=self._current_line_width(),
            grid_line_color=self._grid_line_color,
        )

    def _current_line_width(self) -> float:
        return self.slider_line_width.value() / 100.0

    def _on_line_width_changed(self, value: int):
        self.label_line_width.setText(f"{value / 100.0:.2f} pt")
        self._on_changed()

    def _choose_line_color(self):
        dialog = QColorDialog(QColor(self._grid_line_color), self)
        dialog.setWindowTitle("选择线条颜色")
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        self._localize_color_dialog_buttons(dialog)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        if not color.isValid():
            return
        self._grid_line_color = color.name().upper()
        self._update_color_controls()
        self._on_changed()

    def _localize_color_dialog_buttons(self, dialog: QColorDialog):
        text_map = {
            "OK": "确定",
            "Cancel": "取消",
            "&Pick Screen Color": "吸取屏幕颜色",
            "Pick Screen Color": "吸取屏幕颜色",
            "&Add to Custom Colors": "添加到自定义颜色",
            "Add to Custom Colors": "添加到自定义颜色",
        }
        for button in dialog.findChildren(QPushButton):
            label = button.text().replace("...", "").strip()
            button.setText(text_map.get(label, button.text()))

    def _update_color_controls(self):
        self.btn_line_color.setText(self._grid_line_color)
        self.btn_line_color.setToolTip(f"当前线条颜色：{self._grid_line_color}")
        self.color_swatch.setStyleSheet(
            f"background: {self._grid_line_color}; border: 1px solid #D1D5DB; border-radius: 4px;"
        )

    def refresh_preview(self):
        try:
            config = self._current_config()
            self._pdf_bytes = self._generator.generate_pdf(config)
            self.preview.load_pdf_bytes(self._pdf_bytes)
            pages = self._generator.build_pages(config)
            cells = sum(page.cell_count for page in pages)
            if config.mode == "questions":
                self.status_message.emit(f"共 {len(config.questions)} 道题，生成 {len(pages)} 页，合计 {cells} 格")
            else:
                self.status_message.emit(f"生成 {len(pages)} 页，每页 600 格")
        except Exception as exc:
            self.status_message.emit(f"申论答题纸预览生成失败：{exc}")

    def export_pdf(self):
        self._ensure_pdf_bytes()
        if not self._pdf_bytes:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出申论答题纸 PDF", "shenlun_answer_sheet.pdf", "PDF文件 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            with open(path, "wb") as f:
                f.write(self._pdf_bytes)
            self.status_message.emit(f"已导出 PDF：{path}")
            QMessageBox.information(self, "导出成功", f"PDF 已保存到：\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def export_images(self):
        self._ensure_pdf_bytes()
        if not self._pdf_bytes:
            return
        directory = QFileDialog.getExistingDirectory(self, "选择图片导出目录")
        if not directory:
            return
        try:
            paths = self._generator.export_pngs(self._pdf_bytes, Path(directory))
            self.status_message.emit(f"已导出 {len(paths)} 张图片：{directory}")
            QMessageBox.information(self, "导出成功", f"已导出 {len(paths)} 张 PNG 图片到：\n{directory}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _ensure_pdf_bytes(self):
        if not self._pdf_bytes:
            self.refresh_preview()
