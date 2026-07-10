"""Top toolbar for PDF conversion actions."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QPushButton, QToolBar


class MainToolbar(QToolBar):
    """Toolbar used by the PDF conversion tool page."""

    home_clicked = pyqtSignal()
    open_clicked = pyqtSignal(str)
    save_clicked = pyqtSignal()
    convert_clicked = pyqtSignal()

    def __init__(self):
        super().__init__("主工具栏")
        self.setMovable(False)

        self.btn_home = QPushButton("<")
        self.btn_home.setToolTip("返回首页")
        self.btn_home.setFixedSize(40, 32)
        self.btn_home.clicked.connect(lambda: self.home_clicked.emit())
        self.btn_home.setStyleSheet(
            "QPushButton { background-color: #F3F4F6; border: 1px solid #E5E7EB; "
            "border-radius: 17px; font-weight: 600; font-size: 16px; color: #374151; }"
            "QPushButton:hover { background-color: #E5E7EB; border-color: #D1D5DB; }"
        )
        self.addWidget(self.btn_home)

        self.addSeparator()

        self.btn_open = QPushButton("📂 打开PDF")
        self.btn_open.setFixedHeight(32)
        self.btn_open.clicked.connect(self._on_open)
        self.addWidget(self.btn_open)

        self.addSeparator()

        self.btn_convert = QPushButton("▶ 开始转换")
        self.btn_convert.setFixedHeight(32)
        self.btn_convert.setEnabled(False)
        self.btn_convert.setProperty("cssClass", "primary")
        self.btn_convert.clicked.connect(lambda: self.convert_clicked.emit())
        self.addWidget(self.btn_convert)

        self.addSeparator()

        self.btn_save = QPushButton("💾 保存PDF")
        self.btn_save.setFixedHeight(32)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(lambda: self.save_clicked.emit())
        self.addWidget(self.btn_save)

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择PDF文件", "", "PDF文件 (*.pdf);;所有文件 (*.*)"
        )
        if path:
            self.open_clicked.emit(path)

    def set_has_output(self, has_output: bool):
        self.btn_save.setEnabled(has_output)

    def set_has_input(self, has_input: bool):
        self.btn_convert.setEnabled(has_input)
