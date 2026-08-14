"""手动双面打印重排主界面。

布局按使用流程分为横向三段：
    ① 文件卡（横跨整行）：选择 PDF，显示文件名与页数统计
    ② 设置卡 ×2（并排）：打印机出纸方式 / 翻面方式，选项与动图演示组合
    ③ 预览与步骤卡：正反面页序预览 + 三步打印说明，生成按钮在卡头右上
"""

from pathlib import Path

import fitz
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from tools.duplex_print.core.reorderer import DuplexReorderer
from tools.duplex_print.ui.animations import PaperExitDemo, PaperFlipDemo
from ui.dialogs import show_success

# ============================================================
#  Design tokens (Slate + Indigo)
# ============================================================

CARD_STYLE = (
    "QWidget#card {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 12px;"
    "}"
)

PRIMARY_BTN = (
    "QPushButton {"
    "  background-color: #4F46E5;"
    "  color: #FFFFFF;"
    "  border: none;"
    "  border-radius: 8px;"
    "  padding: 8px 20px;"
    "  font-size: 13px;"
    "  font-weight: 600;"
    "  min-height: 34px;"
    "}"
    "QPushButton:hover { background-color: #4338CA; }"
    "QPushButton:pressed { background-color: #3730A3; }"
    "QPushButton:disabled { background-color: #C7D2FE; color: #FFFFFF; }"
)

RADIO_STYLE = (
    "QRadioButton { font-size: 13px; color: #374151; background: transparent;"
    " border: none; padding: 3px 0; }"
    "QRadioButton::indicator { width: 14px; height: 14px; }"
)

HINT_STYLE = (
    "font-size: 12px; color: #B45309; background-color: #FFFBEB;"
    " border: 1px solid #FDE68A; border-radius: 6px; padding: 6px 10px;"
)

CARD_TITLE_STYLE = (
    "font-size: 14px; font-weight: 700; color: #111827; background: transparent; border: none;"
)

SUBTLE_STYLE = (
    "font-size: 12px; color: #9CA3AF; background: transparent; border: none;"
)

BADGE_STYLE = (
    "font-size: 11px; font-weight: 600; color: #4F46E5;"
    " background-color: #EEF2FF; border-radius: 10px; padding: 2px 10px;"
)

FILE_NAME_STYLE = (
    "font-size: 14px; font-weight: 600; color: #1F2937; background: transparent; border: none;"
)

# 未选择文件时的常态样式：灰色虚线边框提示"可拖放文件到此处"
FILE_CARD_IDLE_STYLE = (
    "QWidget#card {"
    "  background-color: #FFFFFF;"
    "  border: 2px dashed #D1D5DB;"
    "  border-radius: 12px;"
    "}"
)

# 拖入悬停时的样式：靛蓝虚线高亮
FILE_CARD_DRAG_STYLE = (
    "QWidget#card {"
    "  background-color: #EEF2FF;"
    "  border: 2px dashed #4F46E5;"
    "  border-radius: 12px;"
    "}"
)


class DuplexPrintWidget(QWidget):
    """手动双面打印重排：为单面打印机生成正/反面两份打印文件。"""

    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._src_path: str | None = None
        self._page_count = 0
        self._file_card: QWidget | None = None
        self._external_pdf_drag = False
        self.setAcceptDrops(True)
        self._setup_ui()
        self._connect_signals()

    # ============================================================
    #  UI 构建
    # ============================================================

    def _setup_ui(self):
        self.setObjectName("tool-page")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(12)
        self._build_header(root)

        # ① 文件卡
        root.addWidget(self._build_file_card())

        # ② 设置卡并排
        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)
        settings_row.addWidget(self._build_option_card("out"), stretch=1)
        settings_row.addWidget(self._build_option_card("flip"), stretch=1)
        root.addLayout(settings_row)

        # ③ 预览与步骤卡
        root.addWidget(self._build_preview_card(), stretch=1)

        self._refresh_preview()
        self._refresh_steps()

    def _build_header(self, root: QVBoxLayout):
        header = QHBoxLayout()
        header.setSpacing(12)

        self.btn_back = QPushButton("←")
        self.btn_back.setObjectName("btn-back")
        self.btn_back.setToolTip("返回首页")
        header.addWidget(self.btn_back)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)

        title = QLabel("🖨️ 手动双面打印重排")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #111827; background: transparent; border: none;")
        title_col.addWidget(title)

        subtitle = QLabel("为单面打印机生成正/反面两份文件，打印两次实现双面打印")
        subtitle.setStyleSheet(SUBTLE_STYLE)
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()
        root.addLayout(header)

    def _build_file_card(self) -> QWidget:
        """① 文件卡：PDF 图标 + 文件名/页数 + 选择按钮。"""
        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet(FILE_CARD_IDLE_STYLE)
        self._file_card = card
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        icon = QLabel("📄")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "background-color: #EEF2FF; border-radius: 10px; font-size: 22px;"
        )
        layout.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.label_file = QLabel("尚未选择 PDF 文件")
        self.label_file.setStyleSheet(FILE_NAME_STYLE)
        text_col.addWidget(self.label_file)
        self.label_pages = QLabel("点击「选择 PDF」，或将 PDF 文件直接拖入此窗口，松开即加载")
        self.label_pages.setStyleSheet(SUBTLE_STYLE)
        text_col.addWidget(self.label_pages)
        layout.addLayout(text_col, stretch=1)

        self.btn_choose = QPushButton("选择 PDF")
        self.btn_choose.setStyleSheet(PRIMARY_BTN)
        layout.addWidget(self.btn_choose)
        return card

    def _build_option_card(self, kind: str) -> QWidget:
        """② 设置卡：标题 + 选项组 + 动图演示。kind 为 'out'（出纸）或 'flip'（翻面）。"""
        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 卡头：标题 + 当前选中值徽章
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("🖨️ 打印机出纸方式" if kind == "out" else "🔄 反面文字方向")
        title.setStyleSheet(CARD_TITLE_STYLE)
        title_row.addWidget(title)
        title_row.addStretch()
        badge = QLabel()
        badge.setStyleSheet(BADGE_STYLE)
        title_row.addWidget(badge)
        layout.addLayout(title_row)

        # 选项组（同一父容器内的 QRadioButton 自动互斥）
        options = QWidget()
        options_layout = QVBoxLayout(options)
        options_layout.setContentsMargins(2, 0, 2, 0)
        options_layout.setSpacing(4)
        if kind == "out":
            self.radio_face_down = QRadioButton("印好一面朝下 · 多数激光打印机")
            self.radio_face_down.setStyleSheet(RADIO_STYLE)
            self.radio_face_down.setChecked(True)
            self.radio_face_up = QRadioButton("印好一面朝上 · 多数喷墨打印机")
            self.radio_face_up.setStyleSheet(RADIO_STYLE)
            options_layout.addWidget(self.radio_face_down)
            options_layout.addWidget(self.radio_face_up)
            demo = PaperExitDemo()
            self.exit_demo = demo
            self.badge_out = badge
        else:
            self.radio_same = QRadioButton("反面文字与正面同向（推荐）· 自动旋转反面页")
            self.radio_same.setStyleSheet(RADIO_STYLE)
            self.radio_same.setChecked(True)
            self.radio_opposite = QRadioButton("反面文字与正面相反 · 反面页不旋转")
            self.radio_opposite.setStyleSheet(RADIO_STYLE)
            options_layout.addWidget(self.radio_same)
            options_layout.addWidget(self.radio_opposite)
            demo = PaperFlipDemo()
            self.flip_demo = demo
            self.badge_flip = badge
        layout.addWidget(options)

        # 翻面方向依赖打印机与翻面习惯，提示试打校准
        if kind == "flip":
            hint = QLabel("按动画演示翻面即可；若试打发现方向仍不对，切换上面的选项后重新生成")
            hint.setStyleSheet(
                "font-size: 11px; color: #B45309; background: transparent; border: none;"
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)

        # 动图演示
        layout.addWidget(demo, stretch=1)
        return card

    def _build_preview_card(self) -> QWidget:
        """③ 预览与步骤卡：页码预览 + 三步打印说明 + 生成按钮。"""
        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        # 卡头：标题 + 生成按钮（下一步行动在视觉焦点位置）
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("📋 页序预览与打印步骤")
        title.setStyleSheet(CARD_TITLE_STYLE)
        title_row.addWidget(title)
        title_row.addStretch()
        self.btn_generate = QPushButton("🖨️ 生成两份打印文件")
        self.btn_generate.setStyleSheet(PRIMARY_BTN)
        self.btn_generate.setEnabled(False)
        title_row.addWidget(self.btn_generate)
        layout.addLayout(title_row)

        content = QHBoxLayout()
        content.setSpacing(16)
        content.addLayout(self._build_preview_column("front"), stretch=2)
        content.addLayout(self._build_preview_column("back"), stretch=2)
        content.addLayout(self._build_steps_column(), stretch=3)
        layout.addLayout(content, stretch=1)

        # 奇数页提示（默认隐藏）
        self.hint_odd = QLabel()
        self.hint_odd.setStyleSheet(HINT_STYLE)
        self.hint_odd.setWordWrap(True)
        self.hint_odd.setVisible(False)
        layout.addWidget(self.hint_odd)
        return card

    def _build_preview_column(self, side: str) -> QVBoxLayout:
        """构建页序预览列，side 为 'front' 或 'back'。"""
        col = QVBoxLayout()
        col.setSpacing(4)

        label = QLabel()
        label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #6B7280; background: transparent; border: none;"
        )
        col.addWidget(label)

        pages = QLabel()
        pages.setStyleSheet("background: transparent; border: none;")
        pages.setWordWrap(True)
        pages.setTextFormat(Qt.TextFormat.RichText)
        pages.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        col.addWidget(pages, stretch=1)

        if side == "front":
            self.label_front_title = label
            self.label_front = pages
        else:
            self.label_back_title = label
            self.label_back = pages
        return col

    def _build_steps_column(self) -> QVBoxLayout:
        """构建三步打印说明列。"""
        col = QVBoxLayout()
        col.setSpacing(4)

        title = QLabel("三步打印")
        title.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #6B7280; background: transparent; border: none;"
        )
        col.addWidget(title)

        self.label_steps = QLabel()
        self.label_steps.setStyleSheet(
            "font-size: 12px; color: #374151; background: transparent; border: none;"
        )
        self.label_steps.setWordWrap(True)
        self.label_steps.setTextFormat(Qt.TextFormat.RichText)
        self.label_steps.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self.label_steps, stretch=1)
        return col

    def _connect_signals(self):
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.btn_choose.clicked.connect(self._on_choose_file)
        self.btn_generate.clicked.connect(self._on_generate)
        for radio in (
            self.radio_face_down,
            self.radio_face_up,
            self.radio_same,
            self.radio_opposite,
        ):
            radio.toggled.connect(self._on_options_changed)

    # ============================================================
    #  交互逻辑
    # ============================================================

    def _on_choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择PDF文件", "", "PDF文件 (*.pdf);;所有文件 (*.*)")
        if path:
            self._load_pdf(path)

    def _load_pdf(self, path: str):
        """加载 PDF 文件并刷新界面，供文件对话框与拖放共用。"""
        try:
            doc = fitz.open(path)
            count = doc.page_count
            doc.close()
        except Exception as exc:
            QMessageBox.critical(self, "打开失败", f"无法读取PDF文件：\n{exc}")
            return
        self._src_path = path
        self._page_count = count
        self.label_file.setText(Path(path).name)
        self.label_file.setToolTip(path)
        self.btn_generate.setEnabled(True)
        self._file_card.setStyleSheet(CARD_STYLE)
        self._refresh_preview()
        self._refresh_steps()
        self.status_message.emit(f"手动双面打印 - 已加载 {count} 页：{Path(path).name}")

    # ============================================================
    #  拖放支持：拖入 PDF 时高亮文件卡，松开即加载
    # ============================================================

    def dragEnterEvent(self, event: QDragEnterEvent | None):
        if event and event.mimeData() and self._has_external_pdf(event.mimeData()):
            self._external_pdf_drag = True
            if self._file_card is not None:
                self._file_card.setStyleSheet(FILE_CARD_DRAG_STYLE)
            # 悬停时给出明确的动作提示
            if self._src_path:
                self.label_pages.setText("松开鼠标，用新文件替换当前文件")
            else:
                self.label_pages.setText("松开鼠标即可加载此 PDF")
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent | None):
        if self._external_pdf_drag and event:
            event.acceptProposedAction()
        elif event:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._reset_drag_highlight()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent | None):
        was_drag = self._external_pdf_drag
        self._reset_drag_highlight()
        if was_drag and event and event.mimeData():
            paths = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.isLocalFile()
                and Path(url.toLocalFile()).suffix.lower() == ".pdf"
            ]
            if paths:
                self._load_pdf(paths[0])
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def _reset_drag_highlight(self):
        self._external_pdf_drag = False
        if self._file_card is not None:
            # 已选文件恢复实线卡片；未选时保持虚线提示（可拖放）
            self._file_card.setStyleSheet(
                CARD_STYLE if self._src_path else FILE_CARD_IDLE_STYLE
            )
        self._refresh_preview()  # 恢复文件卡副文案

    @staticmethod
    def _has_external_pdf(mime_data) -> bool:
        if not mime_data.hasUrls():
            return False
        return any(
            url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".pdf"
            for url in mime_data.urls()
        )

    def _on_options_changed(self):
        self.exit_demo.set_face_down(self.radio_face_down.isChecked())
        self.flip_demo.set_rotate(self.radio_same.isChecked())
        self._refresh_preview()
        self._refresh_steps()

    def _front_back_orders(self) -> tuple[list[int], list[int]]:
        """返回 (正面页码, 反面页码)，均为 1-indexed 列表。"""
        front = list(range(1, self._page_count + 1, 2))
        back = list(range(2, self._page_count + 1, 2))
        if self.radio_face_down.isChecked():
            back.reverse()
        return front, back

    def _refresh_preview(self):
        # 设置卡徽章：当前选中值
        self.badge_out.setText("面朝下" if self.radio_face_down.isChecked() else "面朝上")
        self.badge_flip.setText("同向" if self.radio_same.isChecked() else "相反")

        if self._page_count <= 0:
            self.label_pages.setText("点击「选择 PDF」，或将 PDF 文件直接拖入此窗口，松开即加载")
            self.label_front_title.setText("正面")
            self.label_back_title.setText("反面")
            self.label_front.setText("<span style='color:#D1D5DB; font-size:12px;'>—</span>")
            self.label_back.setText("<span style='color:#D1D5DB; font-size:12px;'>—</span>")
            self.hint_odd.setVisible(False)
            return

        front, back = self._front_back_orders()
        rotate_note = ""
        if self.radio_same.isChecked() and back:
            rotate_note = " · 每页旋转 180°"
        self.label_front_title.setText(f"正面 · {len(front)} 页")
        self.label_back_title.setText(f"反面 · {len(back)} 页{rotate_note}")
        self.label_front.setText(
            f"<span style='color:#4F46E5; font-size:12px;'>{', '.join(map(str, front))}</span>"
        )
        if back:
            self.label_back.setText(
                f"<span style='color:#4F46E5; font-size:12px;'>{', '.join(map(str, back))}</span>"
            )
        else:
            self.label_back.setText("<span style='color:#D1D5DB; font-size:12px;'>（无）</span>")
        self.label_pages.setText(
            f"共 {self._page_count} 页 · 正面 {len(front)} 页 · 反面 {len(back)} 页"
        )

        if self._page_count % 2 == 1:
            self.hint_odd.setText(
                f"⚠️ 源文档共 {self._page_count} 页（奇数），最后一张纸的反面为空白，属正常现象。"
            )
            self.hint_odd.setVisible(True)
        else:
            self.hint_odd.setVisible(False)

    def _refresh_steps(self):
        if self._page_count <= 0:
            self.label_steps.setText(
                "<span style='color:#9CA3AF;'>选择 PDF 文件后，这里会显示三步打印说明。</span>"
            )
            return

        front, back = self._front_back_orders()
        if self.radio_same.isChecked():
            flip_desc = "拿起整叠纸左右反转（像翻书页）后放回进纸盒（反面已自动旋转 180°）"
        else:
            flip_desc = "把整叠纸上下翻转（纸头调转）后放回进纸盒（反面不旋转）"
        if not back:
            flip_desc = "（无需翻面）"

        steps = (
            f"<b style='color:#4F46E5;'>① 打印正面</b><br>"
            f"打开「…-正面.pdf」，打印全部 {len(front)} 页<br><br>"
            f"<b style='color:#4F46E5;'>② 翻面放回</b><br>"
            f"{flip_desc}<br><br>"
            f"<b style='color:#4F46E5;'>③ 打印反面</b><br>"
            f"打开「…-反面.pdf」，打印全部 {len(back)} 页"
        )
        if back:
            steps += (
                "<br><br><span style='color:#9CA3AF;'>"
                "小贴士：首次使用建议先试打 2 页核对，"
                "若反面文字颠倒，切换「反面文字方向」后重新生成。"
                "</span>"
            )
        else:
            steps += "<br><br><span style='color:#9CA3AF;'>源文档只有 1 页，无需双面打印。</span>"
        self.label_steps.setText(steps)

    # ============================================================
    #  生成流程
    # ============================================================

    def _on_generate(self):
        if not self._src_path:
            QMessageBox.information(self, "提示", "请先选择 PDF 文件。")
            return

        front, back = self._front_back_orders()
        default_name = Path(self._src_path).name
        base, _ = QFileDialog.getSaveFileName(
            self,
            "选择保存文件名（将生成「基准-正面.pdf」和「基准-反面.pdf」）",
            default_name,
            "PDF文件 (*.pdf)",
        )
        if not base:
            return

        stem = base[:-4] if base.lower().endswith(".pdf") else base
        front_path = f"{stem}-正面.pdf"
        back_path = f"{stem}-反面.pdf"

        # getSaveFileName 只确认基准名，派生名需自查覆盖
        existing = [p for p in (front_path, back_path) if Path(p).exists()]
        if existing and QMessageBox.question(
            self,
            "确认覆盖",
            "以下文件已存在，是否覆盖？\n" + "\n".join(existing),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            front_bytes, back_bytes = DuplexReorderer().reorder(
                self._src_path,
                face_down=self.radio_face_down.isChecked(),
                flip_short_edge=self.radio_same.isChecked(),
            )
            with open(front_path, "wb") as f:
                f.write(front_bytes)
            if back_bytes:
                with open(back_path, "wb") as f:
                    f.write(back_bytes)
        except Exception as exc:
            QMessageBox.critical(self, "生成失败", str(exc))
            self.status_message.emit("手动双面打印 - 生成失败")
            return
        finally:
            QApplication.restoreOverrideCursor()

        if back_bytes:
            self.status_message.emit(
                f"手动双面打印 - 已生成：{front_path}、{back_path}")
            show_success(
                self, "生成完成",
                f"两份打印文件已生成：\n{front_path}\n{back_path}\n\n"
                f"请先打印「{Path(front_path).name}」全部 {len(front)} 页，"
                f"翻面放回后打印「{Path(back_path).name}」全部 {len(back)} 页。",
            )
        else:
            self.status_message.emit(f"手动双面打印 - 已生成：{front_path}")
            show_success(
                self, "生成完成",
                f"源文档只有 1 页，无反面内容。已生成：\n{front_path}",
            )
