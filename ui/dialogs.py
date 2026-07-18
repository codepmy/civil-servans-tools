"""自定义通知对话框 — 无系统提示音，统一样式。"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


SUCCESS_STYLE = """
QDialog {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
}
QLabel#dialog-icon {
    font-size: 32px;
    background: transparent;
    border: none;
}
QLabel#dialog-title {
    font-size: 15px;
    font-weight: 700;
    color: #111827;
    background: transparent;
    border: none;
}
QLabel#dialog-message {
    font-size: 13px;
    color: #6B7280;
    background: transparent;
    border: none;
    line-height: 1.5;
}
"""


class NotificationDialog(QDialog):
    """静默通知弹窗：无系统提示音，统一 modern 样式。"""

    def __init__(
        self,
        title: str,
        message: str,
        icon: str = "✅",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setStyleSheet(SUCCESS_STYLE)
        self.setMinimumWidth(360)
        self.setMaximumWidth(480)

        self._setup_ui(icon, message)

    def _setup_ui(self, icon: str, message: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        # 图标 + 消息
        body = QHBoxLayout()
        body.setSpacing(14)

        icon_label = QLabel(icon)
        icon_label.setObjectName("dialog-icon")
        icon_label.setFixedWidth(40)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(icon_label)

        msg_label = QLabel(message)
        msg_label.setObjectName("dialog-message")
        msg_label.setWordWrap(True)
        body.addWidget(msg_label, stretch=1)

        root.addLayout(body)

        # 确定按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_ok = QPushButton("确定")
        btn_ok.setMinimumWidth(90)
        btn_ok.setStyleSheet(
            "QPushButton {"
            "  background-color: #4F46E5;"
            "  color: #FFFFFF;"
            "  border: none;"
            "  border-radius: 8px;"
            "  padding: 8px 20px;"
            "  font-size: 13px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background-color: #4338CA; }"
            "QPushButton:pressed { background-color: #3730A3; }"
        )
        btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(btn_ok)

        btn_layout.addStretch()
        root.addLayout(btn_layout)


def show_success(parent, title: str, message: str):
    """弹出成功通知（无系统提示音）。"""
    dlg = NotificationDialog(title, message, icon="✅", parent=parent)
    dlg.exec()


def show_info(parent, title: str, message: str):
    """弹出信息通知（无系统提示音）。"""
    dlg = NotificationDialog(title, message, icon="ℹ️", parent=parent)
    dlg.exec()
