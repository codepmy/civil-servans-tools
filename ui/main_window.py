"""Main window for the civil-service exam utility toolbox."""

import html
import json
import os
import traceback
import urllib.error
import urllib.request

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
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

from app_paths import resource_path, user_config_path
from tools.pdf_converter.ui.preview_panel import PreviewPanel
from tools.pdf_converter.ui.progress_dialog import ProgressDialog
from tools.pdf_converter.ui.settings_panel import SettingsPanel
from tools.pdf_converter.ui.toolbar import MainToolbar
from tools.pdf_converter.ui.worker import ConversionWorker
from tools.answer_sheet.core.generator import AnswerSheetGenerator
from tools.answer_sheet.ui.widget import AnswerSheetWidget
from tools.exam_timer.ui.timer_widget import TimerWidget


DEFAULT_APP_METADATA = {
    "version": "1.0.0",
    "authorName": "CodePmy",
    "authorEmail": "codepmy@163.com",
    "updateInfoUrl": "https://gitee.com/peisuer/civil-servans-tools/raw/master/version.json",
}


def _load_app_metadata() -> dict:
    data = dict(DEFAULT_APP_METADATA)
    try:
        path = resource_path("version.json")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            for key in data:
                value = str(loaded.get(key, "")).strip()
                if value:
                    data[key] = value
    except Exception:
        pass
    return data


APP_METADATA = _load_app_metadata()
APP_VERSION = APP_METADATA["version"]
AUTHOR_NAME = APP_METADATA["authorName"]
AUTHOR_EMAIL = APP_METADATA["authorEmail"]
UPDATE_INFO_URL = APP_METADATA["updateInfoUrl"]
PRIMARY_BUTTON_STYLE = (
    "QPushButton { background-color: #4F46E5; color: #FFFFFF; border: none; "
    "border-radius: 6px; padding: 6px 14px; font-size: 13px; font-weight: 600; min-height: 28px; }"
    "QPushButton:hover { background-color: #4338CA; }"
    "QPushButton:pressed { background-color: #3730A3; }"
    "QPushButton:disabled { background-color: #C7D2FE; color: #FFFFFF; }"
)


class UpdateCheckWorker(QThread):
    """Fetch remote version information without blocking the UI."""

    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url: str, timeout: int = 8):
        super().__init__()
        self._url = url
        self._timeout = timeout

    def run(self):
        try:
            request = urllib.request.Request(
                self._url,
                headers={"User-Agent": f"CivilServantsTools/{APP_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = response.read().decode("utf-8-sig").strip()
            if not payload:
                raise ValueError("版本文件为空，请确认 version.json 已上传到 Gitee 仓库 master 分支")
            if payload.startswith("<"):
                raise ValueError("版本文件地址返回了网页内容，请确认 version.json 已上传且 raw 地址可直接访问")
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as exc:
                preview = payload[:120].replace("\n", " ")
                raise ValueError(f"版本文件不是有效 JSON：{exc.msg}。返回内容开头：{preview}") from exc
            if not isinstance(data, dict):
                raise ValueError("版本信息格式不正确")
            self.succeeded.emit(data)
        except (urllib.error.URLError, TimeoutError) as exc:
            if isinstance(exc, urllib.error.HTTPError):
                self.failed.emit(f"版本文件访问失败：HTTP {exc.code}。请确认 version.json 已上传到 Gitee 仓库 master 分支")
            else:
                self.failed.emit(f"无法连接到版本服务器：{exc}")
        except Exception as exc:
            self.failed.emit(f"检查更新失败：{exc}")


class MainWindow(QMainWindow):
    """Main application window: home page plus tool detail pages."""

    def __init__(self):
        super().__init__()
        self._input_path: str | None = None
        self._output_bytes: bytes | None = None
        self._worker: ConversionWorker | None = None
        self._progress_dialog: ProgressDialog | None = None
        self._update_worker: UpdateCheckWorker | None = None
        self._update_check_silent = False

        self.setWindowTitle("公考小工具")
        self.resize(1400, 850)
        self.setMinimumSize(1000, 600)

        from tools.pdf_converter.core.generator.font_manager import FontManager

        self._font_manager = FontManager()
        self._font_manager.register_all()
        self._fonts = self._font_manager.available_fonts()

        self._setup_ui()
        self._connect_signals()
        QTimer.singleShot(800, lambda: self._check_updates(silent=True))

    def _setup_ui(self):
        menubar = self.menuBar()

        help_menu = menubar.addMenu("帮助(&H)")
        self.action_check_updates = QAction("检查更新(&U)", self)
        self.action_check_updates.triggered.connect(self._check_updates)
        help_menu.addAction(self.action_check_updates)
        help_menu.addSeparator()
        action_about = QAction("关于(&A)", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

        # 打赏 — 紧挨着"帮助"菜单右侧
        self.action_donate = QAction("☕ 打赏", self)
        self.action_donate.triggered.connect(self._show_donate_dialog)
        menubar.addAction(self.action_donate)

        self.toolbar = MainToolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.stack = QStackedWidget()
        self.home_page = self._create_home_page()
        self.pdf_tool_page = self._create_pdf_tool_page()
        self.timer_tool_page = TimerWidget()
        self.answer_sheet_page = AnswerSheetWidget(
            self._fonts,
            AnswerSheetGenerator(self._font_manager),
        )
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.pdf_tool_page)
        self.stack.addWidget(self.timer_tool_page)
        self.stack.addWidget(self.answer_sheet_page)
        self.setCentralWidget(self.stack)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.author_label = QLabel(
            f"开发人：{AUTHOR_NAME} | 邮箱：<a href=\"mailto:{AUTHOR_EMAIL}\">{AUTHOR_EMAIL}</a>"
        )
        self.author_label.setTextFormat(Qt.TextFormat.RichText)
        self.author_label.setOpenExternalLinks(False)
        self.author_label.linkActivated.connect(self._open_author_email)
        self.author_label.setStyleSheet("color: #6B7280; padding: 0 8px;")
        self.status_bar.addPermanentWidget(self.author_label)
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

        subtitle = QLabel("面向公务员考试备考的资料处理工具合集")
        subtitle.setObjectName("home-subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        layout.addSpacing(14)
        layout.addLayout(grid)
        layout.addStretch(1)

        tool_names = ["📄 PDF内容格式转换", "⏱ 考试计时器", "📝 申论答题纸",
                      "📋 待开发", "🔧 待开发", "📖 待开发",
                      "🎯 待开发", "💡 待开发", "⚡ 待开发"]
        for index, name in enumerate(tool_names):
            button = QPushButton(name)
            button.setObjectName("tool-card-primary" if index <= 2 else "tool-card-pending")
            button.setMinimumHeight(100)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            row, col = divmod(index, 3)
            grid.addWidget(button, row, col)
            if index == 0:
                button.clicked.connect(self._show_pdf_tool)
            elif index == 1:
                button.clicked.connect(self._show_timer_tool)
            elif index == 2:
                button.clicked.connect(self._show_answer_sheet_tool)
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
        self.status_bar.showMessage("就绪")

    def _show_pdf_tool(self):
        self.stack.setCurrentWidget(self.pdf_tool_page)
        self.toolbar.show()
        self.status_bar.showMessage("PDF内容格式转换 - 请打开一个PDF文件开始")

    def _show_timer_tool(self):
        self.stack.setCurrentWidget(self.timer_tool_page)
        self.toolbar.hide()
        self.status_bar.showMessage("考试计时器 - 选择考试模式开始计时")

    def _show_answer_sheet_tool(self):
        self.stack.setCurrentWidget(self.answer_sheet_page)
        self.toolbar.hide()
        self.status_bar.showMessage("申论答题纸生成器 - 设置页数或题目字数后导出")

    def _connect_signals(self):
        self.toolbar.home_clicked.connect(self._show_home)
        self.toolbar.open_clicked.connect(self._on_open)
        self.toolbar.save_clicked.connect(self._on_save)
        self.toolbar.convert_clicked.connect(self._on_convert)
        self.settings_panel.convert_now.connect(self._on_convert)
        self.timer_tool_page.back_requested.connect(self._show_home)
        self.answer_sheet_page.back_requested.connect(self._show_home)
        self.answer_sheet_page.status_message.connect(self._show_answer_sheet_status)

    def _show_answer_sheet_status(self, message: str):
        if self.stack.currentWidget() == self.answer_sheet_page:
            self.status_bar.showMessage(message)

    def _open_author_email(self, _link: str = ""):
        mailto = f"mailto:{AUTHOR_EMAIL}"
        try:
            if hasattr(os, "startfile"):
                os.startfile(mailto)
            else:
                QDesktopServices.openUrl(QUrl(mailto))
        except Exception as exc:
            QMessageBox.warning(self, "打开邮箱失败", f"无法唤起默认邮件客户端：\n{exc}")

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

    def _check_updates(self, silent: bool = False):
        if self._update_worker and self._update_worker.isRunning():
            if silent:
                return
            QMessageBox.information(self, "检查更新", "正在检查更新，请稍候。")
            return

        self._update_check_silent = silent
        if not silent:
            self.action_check_updates.setEnabled(False)
            self.status_bar.showMessage("正在检查更新...")
        self._update_worker = UpdateCheckWorker(UPDATE_INFO_URL)
        self._update_worker.succeeded.connect(self._on_update_info_loaded)
        self._update_worker.failed.connect(self._on_update_check_failed)
        self._update_worker.finished.connect(self._on_update_check_finished)
        self._update_worker.start()

    def _on_update_info_loaded(self, data: dict):
        remote_version = str(data.get("version", "")).strip()
        if not remote_version:
            if self._update_check_silent:
                return
            QMessageBox.warning(self, "检查更新", "版本信息文件中缺少 version 字段。")
            self.status_bar.showMessage("检查更新失败：版本信息不完整")
            return

        if self._is_newer_version(remote_version, APP_VERSION):
            if self._update_check_silent and self._load_skip_update_version() == remote_version:
                return
            self._show_update_available(data, remote_version)
            self.status_bar.showMessage(f"发现新版本 {remote_version}")
        else:
            if self._update_check_silent:
                return
            QMessageBox.information(
                self,
                "检查更新",
                f"当前已是最新版本。\n\n当前版本：{APP_VERSION}\n远程版本：{remote_version}",
            )
            self.status_bar.showMessage("当前已是最新版本")

    def _show_update_available(self, data: dict, remote_version: str):
        release_date = str(data.get("releaseDate", "未知"))
        changelog = str(data.get("changelog", "暂无更新说明"))
        download_url = str(data.get("downloadUrl", "")).strip()
        mandatory = bool(data.get("mandatory", False))
        mandatory_text = "是" if mandatory else "否"
        changelog_html = html.escape(changelog).replace("\n", "<br>")
        download_html = f"<br><br>下载地址：{html.escape(download_url)}" if download_url else ""

        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle("发现新版本")
        message.setTextFormat(Qt.TextFormat.RichText)
        message.setText(
            f"发现新版本 {html.escape(remote_version)}<br><br>"
            "<span style='color:#B91C1C; font-size:15px; font-weight:700;'>请先卸载旧版本</span>"
        )
        chk_skip = QCheckBox("不再提示此版本更新")
        message.setCheckBox(chk_skip)
        message.setInformativeText(
            f"当前版本：{html.escape(APP_VERSION)}<br>"
            f"发布日期：{html.escape(release_date)}<br>"
            f"强制更新：{html.escape(mandatory_text)}<br><br>"
            f"更新内容：<br>{changelog_html}"
            f"{download_html}"
        )
        open_button = None
        if download_url:
            open_button = message.addButton("打开下载页", QMessageBox.ButtonRole.AcceptRole)
            open_button.setProperty("cssClass", "primary")
            open_button.setStyleSheet(PRIMARY_BUTTON_STYLE)
        message.addButton("稍后", QMessageBox.ButtonRole.RejectRole)
        message.exec()

        if chk_skip.isChecked():
            self._save_skip_update_version(remote_version)

        if open_button and message.clickedButton() == open_button:
            self._open_download_url(download_url)

    def _open_download_url(self, download_url: str):
        url = QUrl.fromUserInput(download_url)
        if not url.isValid() or not url.scheme():
            QMessageBox.warning(self, "打开下载页", f"下载地址无效：\n{download_url}")
            return
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "打开下载页", f"无法打开浏览器，请手动访问：\n{download_url}")

    def _on_update_check_failed(self, error_msg: str):
        if self._update_check_silent:
            return
        QMessageBox.warning(self, "检查更新", error_msg)
        self.status_bar.showMessage("检查更新失败")

    def _on_update_check_finished(self):
        self.action_check_updates.setEnabled(True)
        if self._update_worker:
            self._update_worker.deleteLater()
        self._update_worker = None
        self._update_check_silent = False

    @staticmethod
    def _is_newer_version(remote: str, current: str) -> bool:
        return MainWindow._version_tuple(remote) > MainWindow._version_tuple(current)

    @staticmethod
    def _version_tuple(version: str) -> tuple[int, ...]:
        parts: list[int] = []
        for raw_part in version.strip().lstrip("vV").split("."):
            number = ""
            for char in raw_part:
                if not char.isdigit():
                    break
                number += char
            parts.append(int(number or 0))
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)

    @staticmethod
    def _format_error(error: Exception) -> str:
        detail = traceback.format_exc(limit=6)
        return f"{error}\n\n详细信息:\n{detail}"

    def _load_skip_update_version(self) -> str:
        """Load the remote version that the user chose to skip."""
        try:
            path = user_config_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return str(data.get("skip_update_version", "")).strip()
        except Exception:
            pass
        return ""

    def _save_skip_update_version(self, version: str):
        """Save the remote version to skip for auto-update reminders."""
        try:
            path = user_config_path()
            existing = {}
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            existing["skip_update_version"] = version
            path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _show_donate_dialog(self):
        poster_path = resource_path("resources", "author-support-poster.png")
        dialog = QDialog(self)
        dialog.setWindowTitle("打赏作者")
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setStyleSheet("QDialog { background-color: #FFFFFF; }")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("感谢您的支持！")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #1F2937;")
        layout.addWidget(title)

        if poster_path.exists():
            pixmap = QPixmap(str(poster_path))
            if not pixmap.isNull():
                # Scale poster to fit within a reasonable dialog size
                scaled = pixmap.scaled(
                    500, 650,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                image_label = QLabel()
                image_label.setPixmap(scaled)
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(image_label)
                dialog.resize(scaled.width() + 40, scaled.height() + 80)
            else:
                error_label = QLabel("无法加载打赏图片")
                error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(error_label)
        else:
            error_label = QLabel("打赏图片文件不存在")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(error_label)

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "QPushButton { background-color: #E5E7EB; color: #374151; border: none; "
            "border-radius: 6px; padding: 6px 24px; font-size: 13px; }"
            "QPushButton:hover { background-color: #D1D5DB; }"
        )
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dialog.exec()

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于 公考小工具",
            f"<h3>公考小工具 v{APP_VERSION}</h3>"
            "<p>面向公务员考试的小工具集合。</p>"
            f"<p><b>开发人:</b> {AUTHOR_NAME}<br>"
            f"<b>邮箱:</b> <a href=\"mailto:{AUTHOR_EMAIL}\">{AUTHOR_EMAIL}</a></p>"
            "<p><b>当前工具:</b> PDF内容格式转换、考试计时器、申论答题纸生成器</p>"
            "<p><b>Python + PyQt6 + PyMuPDF + ReportLab</b></p>",
        )
