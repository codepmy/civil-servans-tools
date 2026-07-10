"""Application entry point for 公考小工具."""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from ui.main_window import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("公考小工具")
    app.setOrganizationName("pdfchange")

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

    style_path = os.path.join(os.path.dirname(__file__), "resources", "styles", "app.qss")
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
