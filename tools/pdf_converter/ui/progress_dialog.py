"""转换进度对话框。"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal


class ProgressDialog(QDialog):
    """显示转换进度的模态对话框。"""

    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("正在转换...")
        self.setFixedSize(380, 160)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        self.setStyleSheet("QDialog { background-color: #FFFFFF; border-radius: 10px; }")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        self.label_stage = QLabel("准备中...")
        self.label_stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_stage.setStyleSheet("font-size: 13px; color: #374151; font-weight: 500;")
        layout.addWidget(self.label_stage)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setProperty("cssClass", "link")
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignCenter)

    def update_progress(self, percent: int, stage: str):
        """更新进度显示。"""
        self.progress_bar.setValue(percent)
        self.label_stage.setText(f"{stage}")

    def _on_cancel(self):
        """用户取消操作。"""
        self.cancelled.emit()
        self.reject()
