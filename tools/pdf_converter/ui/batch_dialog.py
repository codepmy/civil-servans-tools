"""批量转换对话框：添加多个PDF → 统一设置 → 批量转换 → 统一保存。"""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.dialogs import show_success
from tools.pdf_converter.core.pipeline import ConversionPipeline
from tools.pdf_converter.ui.settings_panel import SettingsPanel
from tools.pdf_converter.ui.worker import BatchConversionWorker


DRAG_BORDER = (
    "QListWidget { border: 2px dashed #4F46E5; border-radius: 6px; background-color: #EEF2FF; }"
)
NO_DRAG_BORDER = (
    "QListWidget { border: 2px dashed #EF4444; border-radius: 6px; background-color: #FEF2F2; }"
)
DEFAULT_BORDER = (
    "QListWidget { border: 1px solid #E5E7EB; border-radius: 4px; background-color: #FFFFFF; }"
)

PRIMARY_BTN = (
    "QPushButton { background-color: #4F46E5; color: #FFFFFF; border: none; "
    "border-radius: 6px; padding: 6px 14px; font-size: 13px; font-weight: 600; min-height: 28px; }"
    "QPushButton:hover { background-color: #4338CA; }"
    "QPushButton:disabled { background-color: #C7D2FE; }"
)


class DropListWidget(QListWidget):
    """支持拖入 PDF 文件的列表控件。"""

    files_added = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._drag_ok = False

    def dragEnterEvent(self, event: QDragEnterEvent | None):
        if event and event.mimeData() and self._has_pdf(event.mimeData()):
            self._drag_ok = True
            self.setStyleSheet(DRAG_BORDER)
            event.acceptProposedAction()
        elif event:
            self.setStyleSheet(NO_DRAG_BORDER)
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent | None):
        if self._drag_ok and event:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drag_ok = False
        self.setStyleSheet(DEFAULT_BORDER)

    def dropEvent(self, event: QDropEvent | None):
        self._drag_ok = False
        self.setStyleSheet(DEFAULT_BORDER)
        if not event or not event.mimeData():
            return
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".pdf":
                paths.append(url.toLocalFile())
        if paths:
            self.files_added.emit(paths)
            event.acceptProposedAction()

    @staticmethod
    def _has_pdf(mime_data) -> bool:
        if not mime_data.hasUrls():
            return False
        return any(
            url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".pdf"
            for url in mime_data.urls()
        )


class BatchDialog(QDialog):
    """批量转换对话框。"""

    def __init__(self, fonts: list[str], parent=None):
        super().__init__(parent)
        self._fonts = fonts or ["SimSun"]
        self._results: dict[str, bytes] = {}   # filename → pdf_bytes
        self._failed: dict[str, str] = {}       # filename → error
        self._worker: BatchConversionWorker | None = None

        self.setWindowTitle("批量转换")
        self.resize(1200, 700)
        self.setMinimumSize(1000, 550)
        self._setup_ui()
        self._connect_signals()

    # ── UI ────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 左侧：文件列表 + 添加/移除 ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(QLabel("文件列表（支持拖入 PDF）"))

        self.list_widget = DropListWidget()
        self.list_widget.files_added.connect(self._add_paths)
        left_layout.addWidget(self.list_widget, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_add = QPushButton("+ 添加文件")
        self.btn_remove = QPushButton("移除选中")
        self.btn_remove.setEnabled(False)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_remove)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # ── 中间：复用 SettingsPanel ──
        self.settings_panel = SettingsPanel(self._fonts)
        splitter.addWidget(self.settings_panel)

        # ── 右侧：进度 + 结果 ──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        progress_group = QGroupBox("进度与结果")
        pg_layout = QVBoxLayout(progress_group)
        pg_layout.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        pg_layout.addWidget(self.progress_bar)

        self.label_status = QLabel("就绪")
        self.label_status.setStyleSheet("color: #6B7280; font-size: 12px;")
        pg_layout.addWidget(self.label_status)

        self.result_list = QListWidget()
        pg_layout.addWidget(self.result_list, stretch=1)

        right_layout.addWidget(progress_group, stretch=1)

        # 操作按钮
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.btn_start = QPushButton("▶ 开始转换")
        self.btn_start.setStyleSheet(PRIMARY_BTN)
        self.btn_save_all = QPushButton("💾 全部保存")
        self.btn_save_all.setEnabled(False)
        action_row.addWidget(self.btn_start)
        action_row.addWidget(self.btn_save_all)
        action_row.addStretch()
        right_layout.addLayout(action_row)

        splitter.addWidget(right)
        splitter.setSizes([330, 340, 480])
        root.addWidget(splitter)

    def _connect_signals(self):
        self.btn_add.clicked.connect(self._on_add_files)
        self.btn_remove.clicked.connect(self._on_remove_selected)
        self.list_widget.itemSelectionChanged.connect(
            lambda: self.btn_remove.setEnabled(len(self.list_widget.selectedItems()) > 0)
        )
        self.btn_start.clicked.connect(self._on_start)
        self.btn_save_all.clicked.connect(self._on_save_all)

    # ── 逻辑 ─────────────────────────────────────────────────

    def _add_paths(self, paths: list[str]):
        existing = {self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.list_widget.count())}
        added = 0
        for p in paths:
            if p in existing:
                continue
            item = QListWidgetItem(Path(p).name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(p)
            self.list_widget.addItem(item)
            existing.add(p)
            added += 1
        if added:
            self.label_status.setText(f"已添加 {added} 个文件，共 {self.list_widget.count()} 个")

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择PDF文件", "", "PDF文件 (*.pdf);;所有文件 (*.*)"
        )
        if paths:
            self._add_paths(paths)

    def _on_remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def _on_start(self):
        paths = [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self.list_widget.count())]
        if not paths:
            QMessageBox.information(self, "提示", "请先添加PDF文件。")
            return

        self._results.clear()
        self._failed.clear()
        self.result_list.clear()
        self.btn_start.setEnabled(False)
        self.btn_save_all.setEnabled(False)
        self.progress_bar.setValue(0)

        # Get config from the shared SettingsPanel (main thread — safe for fonts)
        config = self.settings_panel.get_config()
        template_name = config.get("template", "xingce")

        # Pre-create pipeline in main thread so ReportLab font
        # registration happens on the main thread.
        pipeline = ConversionPipeline()

        self._worker = BatchConversionWorker(pipeline, paths, template_name, config)
        self._worker.overall_progress.connect(self._on_overall_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.file_failed.connect(self._on_file_failed)
        self._worker.all_finished.connect(self._on_all_finished)
        self._worker.start()

    def _on_overall_progress(self, current: int, total: int, filename: str):
        pct = int(current / max(total, 1) * 100)
        self.progress_bar.setValue(pct)
        self.label_status.setText(f"转换中… {current}/{total}  —  {filename}")

    def _on_file_done(self, filename: str, pdf_bytes: bytes):
        self._results[filename] = pdf_bytes
        self.result_list.addItem(f"✓ {filename}")

    def _on_file_failed(self, filename: str, error: str):
        self._failed[filename] = error
        item = QListWidgetItem(f"✗ {filename}  —  {error.split(chr(10))[0][:100]}")
        item.setToolTip(error)
        self.result_list.addItem(item)

    def _on_all_finished(self):
        ok = len(self._results)
        fail = len(self._failed)
        self.label_status.setText(f"完成！成功 {ok} 个，失败 {fail} 个")
        self.btn_start.setEnabled(True)
        self.btn_save_all.setEnabled(ok > 0)
        self.progress_bar.setValue(100)

    def _on_save_all(self):
        if not self._results:
            return
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not directory:
            return
        out_dir = Path(directory)
        saved = 0
        for filename, pdf_bytes in self._results.items():
            stem = Path(filename).stem
            out_path = out_dir / f"{stem}_转换后.pdf"
            counter = 1
            while out_path.exists():
                out_path = out_dir / f"{stem}_转换后({counter}).pdf"
                counter += 1
            out_path.write_bytes(pdf_bytes)
            saved += 1
        show_success(self, "保存完成", f"已保存 {saved} 个文件到：\n{directory}")
