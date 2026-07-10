"""Main window for the civil-service exam utility toolbox."""

import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ui.preview_panel import PreviewPanel
from ui.progress_dialog import ProgressDialog
from ui.settings_panel import SettingsPanel
from ui.toolbar import MainToolbar
from ui.worker import ConversionWorker


class MainWindow(QMainWindow):
    """Main application window: home page plus tool detail pages."""

    def __init__(self):
        super().__init__()
        self._input_path: str | None = None
        self._output_bytes: bytes | None = None
        self._worker: ConversionWorker | None = None
        self._progress_dialog: ProgressDialog | None = None

        self.setWindowTitle("公考小工具")
        self.resize(1400, 850)
        self.setMinimumSize(1000, 600)

        from core.generator.font_manager import FontManager

        self._font_manager = FontManager()
        self._font_manager.register_all()
        self._fonts = self._font_manager.available_fonts()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")

        self.action_open = QAction("打开PDF(&O)...", self)
        self.action_open.setShortcut("Ctrl+O")
        self.action_open.triggered.connect(self._on_open)
        file_menu.addAction(self.action_open)

        self.action_save = QAction("保存结果(&S)...", self)
        self.action_save.setShortcut("Ctrl+S")
        self.action_save.triggered.connect(self._on_save)
        file_menu.addAction(self.action_save)

        file_menu.addSeparator()

        action_home = QAction("返回首页(&H)", self)
        action_home.triggered.connect(self._show_home)
        file_menu.addAction(action_home)

        file_menu.addSeparator()

        action_exit = QAction("退出(&X)", self)
        action_exit.setShortcut("Alt+F4")
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

        help_menu = menubar.addMenu("帮助(&H)")
        action_about = QAction("关于(&A)", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

        self.toolbar = MainToolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.stack = QStackedWidget()
        self.home_page = self._create_home_page()
        self.pdf_tool_page = self._create_pdf_tool_page()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.pdf_tool_page)
        self.setCentralWidget(self.stack)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._show_home()

    def _create_home_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("home-page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 42, 56, 54)
        layout.setSpacing(18)

        title = QLabel("公考小工具")
        title.setObjectName("home-title")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title)

        subtitle = QLabel("选择一个工具开始使用")
        subtitle.setObjectName("home-subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        layout.addSpacing(10)
        layout.addLayout(grid)
        layout.addStretch(1)

        tools = ["pdf格式转换"] + ["待开发中"] * 8
        for index, name in enumerate(tools):
            button = QPushButton(name)
            button.setObjectName("tool-card-primary" if index == 0 else "tool-card-pending")
            button.setMinimumHeight(116)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            row, col = divmod(index, 3)
            grid.addWidget(button, row, col)
            if index == 0:
                button.clicked.connect(self._show_pdf_tool)
            else:
                button.setEnabled(False)

        return page

    def _create_pdf_tool_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.settings_panel = SettingsPanel(self._fonts)
        self.settings_panel.setMinimumWidth(250)
        self.settings_panel.setMaximumWidth(350)

        self.preview_panel = PreviewPanel()

        splitter.addWidget(self.preview_panel)
        splitter.addWidget(self.settings_panel)
        splitter.setSizes([1050, 300])

        layout.addWidget(splitter)
        return page

    def _show_home(self):
        self.stack.setCurrentWidget(self.home_page)
        self.toolbar.hide()
        self.action_open.setEnabled(False)
        self.action_save.setEnabled(False)
        self.status_bar.showMessage("就绪 - 请选择一个小工具")

    def _show_pdf_tool(self):
        self.stack.setCurrentWidget(self.pdf_tool_page)
        self.toolbar.show()
        self.action_open.setEnabled(True)
        self.action_save.setEnabled(True)
        self.status_bar.showMessage("pdf格式转换 - 请打开一个PDF文件开始")

    def _connect_signals(self):
        self.toolbar.home_clicked.connect(self._show_home)
        self.toolbar.open_clicked.connect(self._on_open)
        self.toolbar.save_clicked.connect(self._on_save)
        self.toolbar.convert_clicked.connect(self._on_convert)
        self.settings_panel.convert_now.connect(self._on_convert)

    def _on_open(self, path: str = None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择PDF文件", "", "PDF文件 (*.pdf);;所有文件 (*.*)"
            )
        if not path:
            return

        self._show_pdf_tool()
        self._input_path = path
        self._output_bytes = None

        try:
            self.preview_panel.load_input(path)
            self.toolbar.set_has_input(True)
            self.toolbar.set_has_output(False)
            self.status_bar.showMessage(f"已加载: {path}")
        except Exception as e:
            QMessageBox.warning(self, "加载失败", f"无法加载PDF文件:\n{self._format_error(e)}")

    def _on_convert(self):
        if not self._input_path:
            QMessageBox.information(self, "提示", "请先打开一个PDF文件。")
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在转换中，请稍候。")
            return

        try:
            config = self.settings_panel.get_config()
            template_name = config.get("template", "xingce")

            self._progress_dialog = ProgressDialog(self)
            self._progress_dialog.show()

            self._worker = ConversionWorker(self._input_path, template_name, config)
            self._worker.progress.connect(self._on_progress)
            self._worker.succeeded.connect(self._on_finished)
            self._worker.failed.connect(self._on_error)
            self._worker.finished.connect(self._on_worker_finished)
            self._progress_dialog.cancelled.connect(self._on_cancel_convert)
            self._worker.start()
        except Exception as e:
            self._close_progress_dialog()
            self._worker = None
            QMessageBox.critical(self, "转换启动失败", self._format_error(e))
            self.status_bar.showMessage("转换启动失败")

    def _on_progress(self, percent: int, stage: str):
        try:
            if self._progress_dialog:
                self._progress_dialog.update_progress(percent, stage)
        except Exception:
            pass

    def _on_finished(self, pdf_bytes: bytes):
        self._output_bytes = pdf_bytes
        self._close_progress_dialog()

        size_kb = len(pdf_bytes) / 1024
        try:
            import fitz

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages = doc.page_count
            doc.close()
            self.status_bar.showMessage(f"转换完成! 输出 {pages} 页, {size_kb:.1f} KB")
        except Exception:
            self.status_bar.showMessage(f"转换完成! 输出 {size_kb:.1f} KB")

        try:
            self.preview_panel.load_output(pdf_bytes)
        except Exception as e:
            try:
                self.preview_panel.output_preview.image_label.setText(
                    f"转换完成 ({size_kb:.0f}KB)\n预览加载失败，但PDF可以保存。\n{e}"
                )
            except Exception:
                pass

        self.toolbar.set_has_output(True)

    def _on_error(self, error_msg: str):
        self._close_progress_dialog()

        QMessageBox.critical(
            self,
            "转换失败",
            f"转换过程中出现错误:\n\n{error_msg}\n\n请确认PDF内容为公务员考试题目格式。",
        )
        self.status_bar.showMessage("转换失败")

    def _on_worker_finished(self):
        if self._worker:
            try:
                self._worker.deleteLater()
            except Exception:
                pass
        self._worker = None

    def _on_cancel_convert(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self.status_bar.showMessage("正在取消转换...")

    def _on_save(self):
        if not self._output_bytes:
            QMessageBox.information(self, "提示", "请先执行转换。")
            return

        path, _ = QFileDialog.getSaveFileName(self, "保存PDF", "converted.pdf", "PDF文件 (*.pdf)")
        if not path:
            return

        try:
            with open(path, "wb") as f:
                f.write(self._output_bytes)
            self.status_bar.showMessage(f"已保存: {path}")
            QMessageBox.information(self, "保存成功", f"PDF已保存到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", self._format_error(e))
            self.status_bar.showMessage("保存失败")

    def _close_progress_dialog(self):
        if self._progress_dialog:
            try:
                self._progress_dialog.accept()
            except Exception:
                pass
            self._progress_dialog = None

    @staticmethod
    def _format_error(error: Exception) -> str:
        detail = traceback.format_exc(limit=6)
        return f"{error}\n\n详细信息:\n{detail}"

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于 公考小工具",
            "<h3>公考小工具 v1.0</h3>"
            "<p>面向公务员考试资料处理的小工具集合。</p>"
            "<p><b>当前工具:</b> pdf格式转换</p>"
            "<p><b>Python + PyQt6 + PyMuPDF + ReportLab</b></p>",
        )
