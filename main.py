"""Application entry point for 公考小工具."""

import sys
import traceback

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtCore import QDir, QLockFile, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

from app_paths import resource_path
from ui.main_window import MainWindow

# 单实例唤起 IPC：第二个实例连接本地管道通知已运行实例显示主窗口
_IPC_NAME = "CivilServantsTools-IPC"
_IPC_MSG_SHOW = b"show"


def _notify_running_instance() -> None:
    """通知已运行的实例显示主窗口（由第二个实例调用，随后本进程退出）。"""
    socket = QLocalSocket()
    socket.connectToServer(_IPC_NAME)
    if socket.waitForConnected(500):
        socket.write(_IPC_MSG_SHOW)
        socket.waitForBytesWritten(500)
    socket.disconnectFromServer()


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 开机自启动（注册表 Run 键带 --autostart 启动）→ 后台运行到托盘，不显示主窗口
    autostart_mode = "--autostart" in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName("公考小工具")
    app.setOrganizationName("pdfchange")

    # 单实例锁 + 唤起机制：
    # - 已有实例在运行 → 通过本地管道通知其显示主窗口，本实例退出
    # - 本实例持锁 → 创建 IPC 服务，供后续启动的实例（如再次点击桌面图标）唤起
    lock = QLockFile(QDir.temp().filePath("civilservants_tools.lock"))
    if not lock.tryLock(100):
        _notify_running_instance()
        sys.exit(0)

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
        qss = style_path.read_text(encoding="utf-8")
        # 将 %RESOURCES% 替换为实际资源目录的绝对路径
        res_dir = resource_path("resources")
        qss = qss.replace("%RESOURCES%", res_dir.as_posix())
        app.setStyleSheet(qss)

    window = MainWindow(autostart_mode=autostart_mode)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))

    # 单实例 IPC 服务：收到 "show" → 唤起主窗口
    ipc_server = QLocalServer()

    def _on_ipc_new_connection():
        while ipc_server.hasPendingConnections():
            conn = ipc_server.nextPendingConnection()
            conn.readyRead.connect(lambda c=conn: _on_ipc_data(c))

    def _on_ipc_data(conn):
        data = bytes(conn.readAll())
        if _IPC_MSG_SHOW in data:
            window._show_from_tray()
        conn.disconnectFromServer()
        conn.deleteLater()

    if not ipc_server.listen(_IPC_NAME):
        # 残留管道（异常退出等）→ 清理后重试一次
        QLocalServer.removeServer(_IPC_NAME)
        if ipc_server.listen(_IPC_NAME):
            ipc_server.newConnection.connect(_on_ipc_new_connection)
    else:
        ipc_server.newConnection.connect(_on_ipc_new_connection)

    # 退出前清理截图 OCR 资源（注销全局热键 + 关闭 OCR 子进程）
    app.aboutToQuit.connect(window._cleanup_screenshot_ocr)

    if not autostart_mode:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
