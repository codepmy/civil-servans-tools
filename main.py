"""Application entry point for 公考小工具."""

import sys
import traceback

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from app_paths import resource_path
from ui.main_window import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("公考小工具")
    app.setOrganizationName("pdfchange")

    icon_path = resource_path("resources", "toolsIco.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    def show_unhandled_exception(exc_type, exc_value, exc_tb):
        message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(message, file=sys.stderr)
        try:
            QMessageBox.critical(
                None,
                "程序异常",
                f"程序遇到未处理异常，已阻止直接退出。\n\n{message[-3000:]}",
            )
        except Exception:
            pass

    sys.excepthook = show_unhandled_exception

    style_path = resource_path("resources", "styles", "app.qss")
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
