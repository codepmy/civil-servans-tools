"""错题本主界面。

布局：
    ① 头部：返回按钮 + 标题 + 「添加错题」主按钮
    ② 左侧列表卡：大标签/小标签/关键词三重筛选 + 错题列表 + 底部统计
    ③ 右侧详情卡：大输入框（支持粘贴图片）→ 答案 → 科目 → 模块 → 错因 → 备注 → 操作按钮

设计风格与其它工具页一致（Slate + Indigo design tokens）。
"""

import base64
from collections import Counter

from PyQt6.QtCore import QBuffer, QIODevice, QMimeData, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from tools.mistake_book.core.mistake_book import (
    CATEGORY_NAMES,
    SHENLUN_TAGS,
    XINGCE_TAGS,
    MistakeBookStore,
    MistakeItem,
    collect_image_names,
    embed_images_in_html,
    extract_images_from_html,
    text_preview,
)

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

DANGER_BTN = (
    "QPushButton {"
    "  background-color: #FFFFFF;"
    "  color: #DC2626;"
    "  border: 1px solid #FECACA;"
    "  border-radius: 8px;"
    "  padding: 8px 20px;"
    "  font-size: 13px;"
    "  font-weight: 600;"
    "  min-height: 34px;"
    "}"
    "QPushButton:hover { background-color: #FEF2F2; border-color: #FCA5A5; }"
)

SUBTLE_STYLE = (
    "font-size: 12px; color: #9CA3AF; background: transparent; border: none;"
)

FORM_LABEL_STYLE = (
    "font-size: 12px; font-weight: 600; color: #6B7280; background: transparent; border: none;"
)

INPUT_STYLE = (
    "QLineEdit, QPlainTextEdit, QTextEdit {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #D1D5DB;"
    "  border-radius: 8px;"
    "  padding: 5px 10px;"
    "  font-size: 13px;"
    "  color: #111827;"
    "  selection-background-color: #C7D2FE;"
    "}"
    "QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus { border-color: #4F46E5; }"
    "QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled { background-color: #F9FAFB; color: #9CA3AF; }"
)

COMBO_STYLE = (
    "QComboBox {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #D1D5DB;"
    "  border-radius: 8px;"
    "  padding: 4px 8px;"
    "  font-size: 12px;"
    "  color: #374151;"
    "  min-height: 26px;"
    "}"
    "QComboBox:hover { border-color: #9CA3AF; }"
    "QComboBox::drop-down { border: none; width: 18px; }"
    "QComboBox QAbstractItemView {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 6px;"
    "  selection-background-color: #EEF2FF;"
    "  selection-color: #4F46E5;"
    "  outline: none;"
    "  padding: 4px;"
    "}"
)

# 错题表格：白底、浅灰分隔线、表头浅灰底、选中 indigo 高亮
TABLE_STYLE = (
    "QTableWidget {"
    "  background-color: transparent;"
    "  border: none;"
    "  alternate-background-color: #FAFAF9;"
    "  gridline-color: #F3F4F6;"
    "}"
    "QTableWidget::item {"
    "  padding: 3px 8px;"
    "  border-bottom: 1px solid #F3F4F6;"
    "  font-size: 13px;"
    "  color: #1F2937;"
    "}"
    "QTableWidget::item:selected { background-color: #EEF2FF; color: #1F2937; }"
    "QTableWidget::item:selected:hover { background-color: #E0E7FF; }"
    "QHeaderView::section {"
    "  background-color: #F9FAFB;"
    "  border: none;"
    "  border-bottom: 1px solid #E5E7EB;"
    "  border-right: 1px solid #F3F4F6;"
    "  padding: 6px 8px;"
    "  font-size: 12px;"
    "  font-weight: 600;"
    "  color: #6B7280;"
    "}"
)

# 表格列索引
COL_CATEGORY, COL_TAG, COL_CONTENT, COL_CREATED = range(4)

# 科目列文字颜色：行测 indigo / 申论 amber（与徽标配色一致）
CATEGORY_COLORS = {"xingce": "#4F46E5", "shenlun": "#B45309"}

# 错因预置标签
REASON_TAGS = ["粗心", "时间压力", "蒙的", "题干读错"]

# 标签 chip：未选中（浅紫）/ 选中（indigo 实心）
CHIP_STYLE = (
    "QPushButton {"
    "  background-color: #EEF2FF;"
    "  color: #4F46E5;"
    "  border: none;"
    "  border-radius: 12px;"
    "  padding: 3px 12px;"
    "  font-size: 12px;"
    "  font-weight: 600;"
    "}"
    "QPushButton:hover { background-color: #E0E7FF; }"
    "QPushButton:checked { background-color: #4F46E5; color: #FFFFFF; }"
    "QPushButton:checked:hover { background-color: #4338CA; }"
)

RADIO_STYLE = (
    "QRadioButton { font-size: 13px; color: #374151; background: transparent;"
    " border: none; padding: 2px 0; }"
    "QRadioButton::indicator { width: 14px; height: 14px; }"
)



class _RichTextEditor(QTextEdit):
    """富文本输入框：支持剪贴板图片粘贴 + 中文右键菜单。

    PyQt6 的 QTextEdit 默认 insertFromMimeData 对图片粘贴不生效，
    这里手动插入 QImage；右键菜单改为中文，避免默认英文菜单。
    """

    def insertFromMimeData(self, mime: QMimeData):
        if mime.hasImage():
            image = mime.imageData()
            if isinstance(image, QImage) and not image.isNull():
                # PyQt6 的 insertImage/addResource 均无法把图片带回 toHtml，
                # 改为内嵌 data URI 的 HTML 插入，保存时再提取落盘
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "PNG")
                b64 = base64.b64encode(bytes(buffer.data())).decode("ascii")
                self.insertHtml(f'<img src="data:image/png;base64,{b64}"/>')
                return
        super().insertFromMimeData(mime)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_cut = menu.addAction("剪切", self.cut)
        act_copy = menu.addAction("复制", self.copy)
        act_paste = menu.addAction("粘贴", self.paste)
        menu.addSeparator()
        act_select_all = menu.addAction("全选", self.selectAll)
        cursor = self.textCursor()
        act_cut.setEnabled(cursor.hasSelection())
        act_copy.setEnabled(cursor.hasSelection())
        act_paste.setEnabled(self.canPaste())
        menu.exec(event.globalPos())


class MistakeBookWidget(QWidget):
    """错题本：记录错题、打标签、备注，支持粘贴截图。"""

    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, store: MistakeBookStore | None = None):
        super().__init__()
        self._store = store or MistakeBookStore()
        self._current_id: str | None = None  # None = 新建
        self._loading_item = False  # 加载条目时抑制保存/信号回调
        self._section_chips: dict[str, QPushButton] = {}  # 模块单选 chips
        self._reason_chips: dict[str, QPushButton] = {}  # 错因多选 chips
        self._editor: QTextEdit | None = None
        self._user_sort_section: int | None = None  # None = 未手动排序，默认按创建时间
        # 搜索防抖：连续输入时延迟重建列表，避免每次击键全量刷新卡顿
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._setup_ui()
        self._connect_signals()
        self._rebuild_section_chips()
        self._rebuild_reason_chips([])
        self._refresh_list()
        self._show_empty_state()

    # ============================================================
    #  UI 构建
    # ============================================================

    def _setup_ui(self):
        self.setObjectName("tool-page")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_list_card(), 2)
        body.addWidget(self._build_detail_card(), 3)
        root.addLayout(body, stretch=1)

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(12)

        self.btn_back = QPushButton("←")
        self.btn_back.setObjectName("btn-back")
        self.btn_back.setToolTip("返回首页")
        header.addWidget(self.btn_back)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("📔 错题本")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #111827;"
            " background: transparent; border: none;"
        )
        title_col.addWidget(title)
        subtitle = QLabel("记录错题、打标签、备注，支持粘贴截图，随时回顾")
        subtitle.setStyleSheet(SUBTLE_STYLE)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self.btn_add = QPushButton("＋ 添加错题")
        self.btn_add.setStyleSheet(PRIMARY_BTN)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(self.btn_add)
        return header

    # ---------- 左侧：列表卡 ----------

    def _build_list_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        # 筛选行：大标签 / 小标签 / 搜索
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.combo_category = QComboBox()
        self.combo_category.addItem("全部科目", "")
        self.combo_category.addItem("行测", "xingce")
        self.combo_category.addItem("申论", "shenlun")
        self.combo_category.setStyleSheet(COMBO_STYLE)
        self.combo_category.setMinimumWidth(86)
        filters.addWidget(self.combo_category)

        self.combo_tag = QComboBox()
        self.combo_tag.setStyleSheet(COMBO_STYLE)
        self.combo_tag.setMinimumWidth(96)
        filters.addWidget(self.combo_tag)

        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("搜索题目、备注…")
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.setStyleSheet(INPUT_STYLE)
        filters.addWidget(self.edit_search, stretch=1)
        layout.addLayout(filters)

        # 错题表格
        self.list_widget = QTableWidget(0, 4)
        self.list_widget.setStyleSheet(TABLE_STYLE)
        self.list_widget.setHorizontalHeaderLabels(
            ["科目", "模块", "内容", "创建时间"]
        )
        self.list_widget.verticalHeader().setVisible(False)
        self.list_widget.verticalHeader().setDefaultSectionSize(32)
        self.list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setSortingEnabled(True)
        # 列宽：内容列弹性拉伸，其余固定
        header = self.list_widget.horizontalHeader()
        header.setSectionResizeMode(COL_CATEGORY, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_TAG, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_CONTENT, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_CREATED, QHeaderView.ResizeMode.Fixed)
        self.list_widget.setColumnWidth(COL_CATEGORY, 56)
        self.list_widget.setColumnWidth(COL_TAG, 84)
        # 按当前字体动态计算时间列宽，保证 "2026-08-21 10:00" 完整显示
        time_width = self.list_widget.fontMetrics().horizontalAdvance("2026-08-21 10:00") + 28
        self.list_widget.setColumnWidth(COL_CREATED, max(time_width, 118))
        self.list_widget.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        # 记录用户手动点表头选择的排序列（sortIndicatorSection 默认返回 0，不能作为「未设置」判断）
        header.sortIndicatorChanged.connect(self._on_sort_changed)
        layout.addWidget(self.list_widget, stretch=1)

        # 底部统计
        self.label_count = QLabel("")
        self.label_count.setStyleSheet(SUBTLE_STYLE)
        layout.addWidget(self.label_count)
        return card

    # ---------- 右侧：详情卡 ----------

    def _build_detail_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)

        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(self._build_empty_page())
        self.detail_stack.addWidget(self._build_form_page())
        layout.addWidget(self.detail_stack)
        return card

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addStretch()
        icon = QLabel("📔")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "font-size: 52px; background: transparent; border: none;"
        )
        lay.addWidget(icon)
        tip = QLabel("未选择错题")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #6B7280;"
            " background: transparent; border: none;"
        )
        lay.addWidget(tip)
        hint = QLabel("点击左上角「添加错题」开始记录\n或从左侧列表选择一条错题查看")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(SUBTLE_STYLE)
        lay.addWidget(hint)
        lay.addStretch()
        return page

    def _build_form_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # ① 大输入框（支持粘贴图片）
        editor_box = QWidget()
        editor_lay = QVBoxLayout(editor_box)
        editor_lay.setContentsMargins(0, 0, 0, 0)
        self._editor = _RichTextEditor()
        self._editor.setAcceptRichText(True)
        self._editor.setStyleSheet(INPUT_STYLE)
        editor_lay.addWidget(self._editor)
        self._editor_placeholder = QLabel("在这里粘贴题目文字或截图\n（Ctrl + V 直接粘贴剪贴板图片）")
        self._editor_placeholder.setStyleSheet(
            "font-size: 13px; color: #9CA3AF; background: transparent; border: none;"
        )
        self._editor_placeholder.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._editor_placeholder.setContentsMargins(14, 10, 0, 0)
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._editor_placeholder.setParent(self._editor)
        self._editor_placeholder.show()
        self._editor_placeholder.raise_()
        lay.addWidget(editor_box, stretch=1)

        # ② 答案行
        answer_row = QHBoxLayout()
        answer_row.setSpacing(8)
        answer_row.addWidget(self._form_label("我的答案"))
        self.edit_my_answer = QLineEdit()
        self.edit_my_answer.setPlaceholderText("如 B")
        self.edit_my_answer.setMaximumWidth(110)
        self.edit_my_answer.setStyleSheet(INPUT_STYLE)
        answer_row.addWidget(self.edit_my_answer)
        answer_row.addSpacing(6)
        answer_row.addWidget(self._form_label("正确答案"))
        self.edit_correct_answer = QLineEdit()
        self.edit_correct_answer.setPlaceholderText("如 C")
        self.edit_correct_answer.setMaximumWidth(110)
        self.edit_correct_answer.setStyleSheet(INPUT_STYLE)
        answer_row.addWidget(self.edit_correct_answer)
        answer_row.addSpacing(10)
        self.check_corrected = QCheckBox("已订正")
        self.check_corrected.setStyleSheet(RADIO_STYLE)
        answer_row.addWidget(self.check_corrected)
        answer_row.addStretch()
        lay.addLayout(answer_row)

        # ③ 科目（大标签）
        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        category_row.addWidget(self._form_label("科目"))
        self.radio_xingce = QRadioButton("行测")
        self.radio_xingce.setStyleSheet(RADIO_STYLE)
        self.radio_xingce.setChecked(True)
        self.radio_shenlun = QRadioButton("申论")
        self.radio_shenlun.setStyleSheet(RADIO_STYLE)
        category_row.addWidget(self.radio_xingce)
        category_row.addWidget(self.radio_shenlun)
        category_row.addStretch()
        lay.addLayout(category_row)

        # ④ 模块（单选 chips，随科目联动）
        section_row = QHBoxLayout()
        section_row.setSpacing(8)
        section_row.addWidget(self._form_label("模块"))
        self.section_chips_box = QWidget()
        self.section_chips_lay = QHBoxLayout(self.section_chips_box)
        self.section_chips_lay.setContentsMargins(0, 0, 0, 0)
        self.section_chips_lay.setSpacing(4)
        section_row.addWidget(self.section_chips_box, stretch=1)
        lay.addLayout(section_row)

        # ⑤ 错因（多选 chips + 自定义输入）
        reason_row = QHBoxLayout()
        reason_row.setSpacing(8)
        reason_row.addWidget(self._form_label("错因"))
        self.reason_chips_box = QWidget()
        self.reason_chips_lay = QHBoxLayout(self.reason_chips_box)
        self.reason_chips_lay.setContentsMargins(0, 0, 0, 0)
        self.reason_chips_lay.setSpacing(4)
        reason_row.addWidget(self.reason_chips_box, stretch=1)
        self.edit_custom_tag = QLineEdit()
        self.edit_custom_tag.setPlaceholderText("自定义错因")
        self.edit_custom_tag.setMaximumWidth(110)
        self.edit_custom_tag.setStyleSheet(INPUT_STYLE)
        reason_row.addWidget(self.edit_custom_tag)
        self.btn_add_tag = QPushButton("＋")
        self.btn_add_tag.setStyleSheet(
            "QPushButton { background-color: #EEF2FF; color: #4F46E5; border: none;"
            " border-radius: 12px; min-width: 26px; max-width: 26px; min-height: 26px;"
            " font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background-color: #E0E7FF; }"
        )
        self.btn_add_tag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_tag.setToolTip("添加自定义错因标签")
        reason_row.addWidget(self.btn_add_tag)
        lay.addLayout(reason_row)

        # ⑤ 备注
        note_row = QHBoxLayout()
        note_row.setSpacing(8)
        note_row.addWidget(self._form_label("备注"))
        self.edit_note = QPlainTextEdit()
        self.edit_note.setPlaceholderText("记录解析思路、错因分析…")
        self.edit_note.setFixedHeight(64)
        self.edit_note.setStyleSheet(INPUT_STYLE)
        note_row.addWidget(self.edit_note, stretch=1)
        lay.addLayout(note_row)

        # ⑥ 操作行
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.btn_save = QPushButton("保存")
        self.btn_save.setStyleSheet(PRIMARY_BTN)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        action_row.addWidget(self.btn_save)
        self.btn_delete = QPushButton("删除")
        self.btn_delete.setStyleSheet(DANGER_BTN)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        action_row.addWidget(self.btn_delete)
        action_row.addStretch()
        self.label_time = QLabel("")
        self.label_time.setStyleSheet(SUBTLE_STYLE)
        self.label_time.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        action_row.addWidget(self.label_time)
        lay.addLayout(action_row)
        return page

    def _form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(FORM_LABEL_STYLE)
        return label

    # ============================================================
    #  信号连接
    # ============================================================

    def _connect_signals(self):
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.btn_add.clicked.connect(self._new_item)
        self.btn_save.clicked.connect(self._save_current)
        self.btn_delete.clicked.connect(self._delete_current)

        self.list_widget.currentItemChanged.connect(self._on_select)
        self.combo_category.currentIndexChanged.connect(lambda _: self._refresh_list())
        self.combo_tag.currentIndexChanged.connect(lambda _: self._refresh_list())
        # 搜索防抖：停止输入 200ms 后才刷新；搜索不改变标签选项，无需重建下拉
        self._search_timer.timeout.connect(lambda: self._refresh_list(rebuild_tags=False))
        self.edit_search.textChanged.connect(lambda _: self._search_timer.start())
        self.radio_xingce.toggled.connect(lambda _: self._on_category_changed())
        self.btn_add_tag.clicked.connect(self._add_custom_reason)
        self.edit_custom_tag.returnPressed.connect(self._add_custom_reason)
        self._editor.textChanged.connect(self._update_editor_placeholder)

    # ============================================================
    #  列表
    # ============================================================

    def _refresh_list(self, rebuild_tags: bool = True):
        """按当前筛选条件重建列表，并更新统计与小标签下拉。"""
        items = self._store.all_items()
        category = self.combo_category.currentData()
        tag = self.combo_tag.currentData() or ""
        keyword = self.edit_search.text().strip()

        if category:
            items = [it for it in items if it.category == category]
        if tag:
            items = [it for it in items if tag in it.tags]
        if keyword:
            keyword_lower = keyword.lower()
            items = [
                it for it in items
                if keyword_lower in text_preview(it.content).lower()
                or keyword_lower in it.note.lower()
                or any(keyword_lower in t.lower() for t in it.tags)
            ]

        # 记住当前选中 id 与滚动位置，刷新后在 blockSignals 期间恢复，
        # 避免触发自动保存递归，也避免列表视觉跳动
        selected_id = self._current_id
        scroll_pos = self.list_widget.verticalScrollBar().value()
        self.list_widget.blockSignals(True)
        self.list_widget.setUpdatesEnabled(False)
        self.list_widget.setSortingEnabled(False)  # 填充期间禁用排序
        self.list_widget.clearContents()
        self.list_widget.setRowCount(0)
        for item in items:
            self._append_table_row(item)
        self.list_widget.setSortingEnabled(True)
        # 未手动排序时默认按创建时间倒序；否则保持用户选择的排序列/方向
        header = self.list_widget.horizontalHeader()
        if self._user_sort_section is None:
            section, order = COL_CREATED, Qt.SortOrder.DescendingOrder
        else:
            section = self._user_sort_section
            order = header.sortIndicatorOrder()
        self.list_widget.sortItems(section, order)
        if selected_id:
            for row in range(self.list_widget.rowCount()):
                if self.list_widget.item(row, COL_CATEGORY).data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.list_widget.setCurrentCell(row, 0)
                    break
        self.list_widget.verticalScrollBar().setValue(scroll_pos)
        self.list_widget.setUpdatesEnabled(True)
        self.list_widget.blockSignals(False)

        # 统计
        total = self._store.count()
        uncorrected = sum(1 for it in self._store.all_items() if not it.corrected)
        self.label_count.setText(f"共 {total} 条 · 未订正 {uncorrected} 条")
        self.status_message.emit(f"错题本 - 共 {total} 条错题")

        if rebuild_tags:
            self._refresh_tag_filter_options()

    def _append_table_row(self, item: MistakeItem):
        """按一条错题追加表格行：科目 / 模块 / 内容 / 创建时间。"""
        row = self.list_widget.rowCount()
        self.list_widget.insertRow(row)

        # 所有列的单元格都携带条目 id：点击整行任意一列都能定位详情
        cell_items = []

        # 科目（按科目着色）
        cat_item = QTableWidgetItem(CATEGORY_NAMES.get(item.category, item.category))
        cat_item.setForeground(QColor(CATEGORY_COLORS.get(item.category, "#6B7280")))
        cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        cell_items.append(cat_item)

        # 模块（独立字段，如"数量关系"）
        cell_items.append(QTableWidgetItem(item.section))

        # 内容摘要：已订正加 ✓ 并置灰
        preview = text_preview(item.content, 40) or "（无内容）"
        if item.corrected:
            preview = "✓ " + preview
        content_item = QTableWidgetItem(preview)
        if item.corrected:
            content_item.setForeground(QColor("#9CA3AF"))
        cell_items.append(content_item)

        # 创建时间
        time_item = QTableWidgetItem(item.created_at)
        time_item.setForeground(QColor("#9CA3AF"))
        cell_items.append(time_item)

        for col, cell in enumerate(cell_items):
            cell.setData(Qt.ItemDataRole.UserRole, item.id)
            self.list_widget.setItem(row, col, cell)

    def _refresh_tag_filter_options(self):
        """小标签筛选下拉：随大标签科目联动（行测/申论各自预置 + 自定义标签）。"""
        current = self.combo_tag.currentData() or ""
        category = self.combo_category.currentData()
        # 收集该科目数据中出现的自定义标签（模块 + 错因）
        seen = set()
        for it in self._store.all_items():
            if category and it.category != category:
                continue
            seen.update(it.tags)
            if it.section:
                seen.add(it.section)
        # 预置标签（模块按科目联动 + 错因）保持定义顺序；自定义标签排在其后
        if category == "xingce":
            preset = list(XINGCE_TAGS) + REASON_TAGS
        elif category == "shenlun":
            preset = list(SHENLUN_TAGS) + REASON_TAGS
        else:
            preset = list(XINGCE_TAGS + SHENLUN_TAGS + REASON_TAGS)
        custom = sorted(seen - set(preset))
        self.combo_tag.blockSignals(True)
        self.combo_tag.clear()
        self.combo_tag.addItem("全部标签", "")
        for t in preset + custom:
            self.combo_tag.addItem(t, t)
        idx = self.combo_tag.findData(current)
        self.combo_tag.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_tag.blockSignals(False)

    # ============================================================
    #  详情表单
    # ============================================================

    def _show_empty_state(self):
        self.detail_stack.setCurrentIndex(0)

    def _show_form(self):
        self.detail_stack.setCurrentIndex(1)

    def _new_item(self):
        """清空表单进入新建状态（未保存的修改直接丢弃，点「保存」才入库）。"""
        self._current_id = None
        self._loading_item = True
        self._editor.clear()
        self.edit_my_answer.clear()
        self.edit_correct_answer.clear()
        self.check_corrected.setChecked(False)
        self.edit_note.clear()
        self.edit_custom_tag.clear()
        self.radio_xingce.setChecked(True)
        self._rebuild_section_chips()
        self._rebuild_reason_chips([])
        self._loading_item = False
        self._update_editor_placeholder()
        # 先清选择（触发 _on_select(None) 显示空态），随后立即切回表单页
        self.list_widget.clearSelection()
        self._show_form()
        self._editor.setFocus()

    def _on_sort_changed(self, section: int, _order):
        """用户点击表头选择排序列时记录（区别于默认的创建时间排序）。"""
        self._user_sort_section = section

    def _on_select(self, current: QTableWidgetItem | None, _previous):
        if self._loading_item:
            return
        if current is None:
            self._current_id = None
            self._show_empty_state()
            return
        # 切换条目不自动保存：仅点「保存」按钮才写入，未保存的修改直接丢弃
        item_id = current.data(Qt.ItemDataRole.UserRole)
        item = self._store.get(item_id)
        if item is None:
            return
        self._current_id = item.id
        self._loading_item = True
        self._editor.setHtml(embed_images_in_html(item.content, self._store.image_dir))
        self.edit_my_answer.setText(item.my_answer)
        self.edit_correct_answer.setText(item.correct_answer)
        self.check_corrected.setChecked(item.corrected)
        self.edit_note.setPlainText(item.note)
        (self.radio_xingce if item.category == "xingce" else self.radio_shenlun).setChecked(True)
        self._loading_item = False
        self._apply_tags(item.section, item.tags)
        self._update_editor_placeholder()
        self._show_form()
        self.label_time.setText(
            f"创建 {item.created_at} · 更新 {item.updated_at}"
        )
        # 自动保存会刷新 updated_at 导致排序变化，这里把列表高亮对齐到当前条目
        self._loading_item = True
        self.list_widget.blockSignals(True)
        for row in range(self.list_widget.rowCount()):
            if self.list_widget.item(row, COL_CATEGORY).data(Qt.ItemDataRole.UserRole) == item_id:
                self.list_widget.setCurrentCell(row, 0)
                break
        self.list_widget.blockSignals(False)
        self._loading_item = False

    # ---------- 模块 / 错因 chips ----------

    @staticmethod
    def _make_chip(name: str, checked: bool = False) -> QPushButton:
        btn = QPushButton(name)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setStyleSheet(CHIP_STYLE)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _clear_layout(self, layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

    def _rebuild_section_chips(self, checked_name: str = ""):
        """按当前科目重建模块单选 chips，仅勾选 checked_name。"""
        self._clear_layout(self.section_chips_lay)
        self._section_chips = {}
        preset = XINGCE_TAGS if self.radio_xingce.isChecked() else SHENLUN_TAGS
        for name in preset:
            btn = self._make_chip(name, name == checked_name)
            btn.clicked.connect(lambda _c, b=btn: self._on_section_chip(b))
            self.section_chips_lay.addWidget(btn)
            self._section_chips[name] = btn
        self.section_chips_lay.addStretch()

    def _on_section_chip(self, btn: QPushButton):
        """模块单选互斥：点击未选中的选中它，点击已选中的取消选择。"""
        for name, b in self._section_chips.items():
            b.setChecked(b is btn and btn.isChecked())

    def _collect_custom_reason_pool(self, limit: int = 8) -> list[str]:
        """从数据中收集用户自定义错因（排除预置），按使用频率取前 limit 个。"""
        counter = Counter()
        for it in self._store.all_items():
            for t in it.tags:
                if t not in REASON_TAGS:
                    counter[t] += 1
        return [name for name, _ in counter.most_common(limit)]

    def _rebuild_reason_chips(self, checked_names: list[str]):
        """重建错因 chips：预置 + 用户自定义建议（按频率），仅勾选 checked_names。

        自定义错因一旦被用过就会沉淀为建议，新建条目时点选即可复用。
        """
        self._clear_layout(self.reason_chips_lay)
        self._reason_chips = {}
        suggestions = self._collect_custom_reason_pool()
        for name in REASON_TAGS + suggestions:
            btn = self._make_chip(name, name in checked_names)
            self.reason_chips_lay.addWidget(btn)
            self._reason_chips[name] = btn
        for name in checked_names:
            if name not in self._reason_chips:  # 不在预置/建议池（如已从数据中消失）
                btn = self._make_chip(name, True)
                self.reason_chips_lay.insertWidget(self.reason_chips_lay.count() - 1, btn)
                self._reason_chips[name] = btn
        self.reason_chips_lay.addStretch()

    def _add_custom_reason(self):
        name = self.edit_custom_tag.text().strip()
        if not name:
            return
        if name in self._reason_chips:
            self._reason_chips[name].setChecked(True)
        else:
            btn = self._make_chip(name, True)
            self.reason_chips_lay.insertWidget(self.reason_chips_lay.count() - 1, btn)
            self._reason_chips[name] = btn
        self.edit_custom_tag.clear()

    def _on_category_changed(self):
        """科目切换：模块 chips 换预置，错因 chips 保持当前选中。"""
        self._rebuild_section_chips()
        self._rebuild_reason_chips(self._collect_reasons())

    def _collect_section(self) -> str:
        for name, btn in self._section_chips.items():
            if btn.isChecked():
                return name
        return ""

    def _collect_reasons(self) -> list[str]:
        tags = [name for name, btn in self._reason_chips.items() if btn.isChecked()]
        custom = self.edit_custom_tag.text().strip()
        if custom and custom not in tags:
            tags.append(custom)
        return tags

    def _apply_tags(self, section: str, tags: list[str]):
        """加载条目：模块单选勾选 section，错因 chips 勾选 tags。

        全量重建并精确勾选，避免上一个条目的选中残留。
        """
        self._rebuild_section_chips(section)
        self._rebuild_reason_chips(tags)

    # ---------- 保存 / 删除 ----------

    def _save_current(self):
        """收集表单 → 图片落盘 → 写入存储 → 刷新列表。

        仅在点击「保存」按钮时调用；切换条目不自动保存。
        """
        if not self._editor.toPlainText().strip():
            self.status_message.emit("内容为空，未保存")
            return

        item_id = self._current_id or MistakeItem.new_id()
        old = self._store.get(item_id) if self._current_id else None

        # 图片落盘 + 清理本条目旧图片
        html = self._editor.toHtml()
        content = extract_images_from_html(html, self._store.image_dir, item_id)
        if old:
            old_names = set(collect_image_names(old.content))
            new_names = set(collect_image_names(content))
            for name in old_names - new_names:
                try:
                    (self._store.image_dir / name).unlink(missing_ok=True)
                except OSError:
                    pass

        now = MistakeItem.now()
        item = MistakeItem(
            id=item_id,
            content=content,
            category="xingce" if self.radio_xingce.isChecked() else "shenlun",
            section=self._collect_section(),
            tags=self._collect_reasons(),
            my_answer=self.edit_my_answer.text().strip(),
            correct_answer=self.edit_correct_answer.text().strip(),
            corrected=self.check_corrected.isChecked(),
            note=self.edit_note.toPlainText().strip(),
            created_at=old.created_at if old else now,
            updated_at=now,
        )
        if old:
            self._store.update(item)
        else:
            self._store.add(item)

        self._current_id = item_id
        self.label_time.setText(f"创建 {item.created_at} · 更新 {item.updated_at}")
        self._refresh_list()
        self.status_message.emit(f"已保存（共 {self._store.count()} 条）")

    def _delete_current(self):
        if not self._current_id:
            return
        answer = QMessageBox.question(
            self,
            "删除错题",
            "确定删除这道错题吗？删除后不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._store.delete(self._current_id)
        self._current_id = None
        self._show_empty_state()
        self._refresh_list()
        self.status_message.emit(f"已删除（剩 {self._store.count()} 条）")

    # ---------- 辅助 ----------

    def _update_editor_placeholder(self):
        """大输入框空内容时显示提示浮层。"""
        self._editor_placeholder.setVisible(not self._editor.toPlainText().strip())
