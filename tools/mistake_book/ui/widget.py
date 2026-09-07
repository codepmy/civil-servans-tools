"""错题本主界面。

布局：
    ① 头部：返回按钮 + 标题 + 「添加错题」主按钮
    ② 左侧列表卡：科目/模块/错因/搜索四条件筛选 + 双行信息错题列表 + 底部统计
    ③ 右侧详情卡：标题 → 答案 → 科目 → 模块 → 错因 → 大输入框（支持粘贴图片）→ 操作按钮

设计风格与其它工具页一致（Slate + Indigo design tokens）。
"""

import base64
import tempfile
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, QMimeData, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFontComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tools.mistake_book.core.mistake_book import (
    MistakeBookConfig,
    MistakeBookStore,
    MistakeItem,
    collect_image_names,
    embed_images_in_html,
    extract_images_from_html,
    shared_config,
    shared_store,
    text_preview,
)
from tools.mistake_book.ui.settings_dialog import EnumSettingsDialog

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

# 头部「枚举配置」次级按钮（白底 indigo 描边，与「＋ 添加错题」主按钮并列）
SECONDARY_BTN = (
    "QPushButton { background-color: #FFFFFF; color: #4F46E5;"
    "  border: 1px solid #C7D2FE; border-radius: 8px; padding: 8px 18px;"
    "  font-size: 13px; font-weight: 600; min-height: 34px; }"
    "QPushButton:hover { background-color: #EEF2FF; border-color: #4F46E5; }"
    "QPushButton:pressed { background-color: #E0E7FF; }"
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

# 表格为单列双行信息布局：每行一个双行富文本 QLabel（见 _append_table_row）
COL_INFO = 0

# 富文本工具栏：荧光笔高亮 / 文字颜色预设
HIGHLIGHT_COLORS = [
    ("黄色", "#FDE68A"), ("绿色", "#BBF7D0"), ("蓝色", "#BFDBFE"),
    ("粉色", "#FBCFE8"), ("橙色", "#FED7AA"), ("青色", "#A5F3FC"),
]
TEXT_COLORS = [
    ("黑色", "#111827"), ("红色", "#DC2626"), ("橙色", "#EA580C"),
    ("绿色", "#16A34A"), ("蓝色", "#2563EB"), ("紫色", "#7C3AED"),
]

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

# 富文本格式工具栏（Slate + Indigo 设计语言：线性图标、分组分隔线、圆角反馈）
FORMATBAR_STYLE = (
    "QWidget#formatbar {"
    "  background-color: #F9FAFB;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 10px;"
    "}"
)

FMT_BTN_STYLE = (
    "QPushButton {"
    "  background: transparent;"
    "  border: none;"
    "  border-radius: 6px;"
    "  min-width: 28px; max-width: 28px;"
    "  min-height: 28px; max-height: 28px;"
    "}"
    "QPushButton:hover { background-color: #EEF2FF; }"
    "QPushButton:checked { background-color: #E0E7FF; }"
    "QPushButton:disabled { background: transparent; }"
)

FMT_TOOLBTN_STYLE = (
    "QToolButton {"
    "  background: transparent;"
    "  border: none;"
    "  border-radius: 6px;"
    "  padding: 3px 8px;"
    "  min-height: 28px;"
    "}"
    "QToolButton:hover { background-color: #EEF2FF; }"
    "QToolButton::menu-indicator { image: none; }"
)

FMT_COMBO_STYLE = (
    "QComboBox {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 7px;"
    "  padding: 3px 6px;"
    "  font-size: 12px;"
    "  color: #374151;"
    "  min-height: 24px;"
    "}"
    "QComboBox:hover { border-color: #C7D2FE; }"
    "QComboBox:focus { border-color: #4F46E5; }"
    # QSS 样式化后原生箭头消失（Qt6 无法用 border 三角、QProxyStyle
    # 也被 QStyleSheetStyle 绕过），改用生成的 PNG 供 image 引用
    "QComboBox::drop-down { border: none; width: 16px; }"
    "QComboBox::down-arrow { image: url({ARROW}); width: 10px; height: 10px; }"
    "QComboBox QLineEdit { border: none; background: transparent; }"
    "QComboBox QAbstractItemView {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 8px;"
    "  selection-background-color: #EEF2FF;"
    "  selection-color: #4F46E5;"
    "  outline: none;"
    "  padding: 4px;"
    "  font-size: 12px;"
    "}"
)

FMT_TEXT_BTN_STYLE = (
    "QPushButton {"
    "  background: transparent;"
    "  border: none;"
    "  border-radius: 6px;"
    "  min-width: 28px; max-width: 28px;"
    "  min-height: 28px; max-height: 28px;"
    "  font-size: 15px;"
    "  font-weight: 600;"
    "  color: #6B7280;"
    "}"
    "QPushButton:hover { background-color: #EEF2FF; color: #4F46E5; }"
    "QPushButton:disabled { background: transparent; color: #D1D5DB; }"
)

# 编辑器下方操作行的主按钮（保存：indigo 实底；删除：红字白底描边）
ACTION_SAVE_BTN = (
    "QPushButton { background-color: #4F46E5; color: #FFFFFF; border: none;"
    "  border-radius: 8px; padding: 9px 30px; font-size: 13px; font-weight: 600;"
    "  min-height: 34px; }"
    "QPushButton:hover { background-color: #4338CA; }"
    "QPushButton:pressed { background-color: #3730A3; }"
    "QPushButton:disabled { background-color: #C7D2FE; color: #FFFFFF; }"
)
ACTION_DELETE_BTN = (
    "QPushButton { background-color: #FFFFFF; color: #DC2626;"
    "  border: 1px solid #FECACA; border-radius: 8px; padding: 9px 24px;"
    "  font-size: 13px; font-weight: 600; min-height: 34px; }"
    "QPushButton:hover { background-color: #FEF2F2; border-color: #FCA5A5; }"
    "QPushButton:disabled { background-color: #F9FAFB; color: #D1D5DB;"
    "  border-color: #F3F4F6; }"
)

FMT_MENU_STYLE = (
    "QMenu {"
    "  background-color: #FFFFFF;"
    "  border: 1px solid #E5E7EB;"
    "  border-radius: 8px;"
    "  padding: 4px;"
    "}"
    "QMenu::item { padding: 5px 22px 5px 8px; border-radius: 6px; font-size: 12px; color: #374151; }"
    "QMenu::item:selected { background-color: #EEF2FF; color: #4F46E5; }"
    "QMenu::separator { height: 1px; background: #F3F4F6; margin: 4px 6px; }"
)

# 格式图标配色：常态灰 / hover 与选中 indigo
ICON_COLOR = "#6B7280"
ICON_ACTIVE = "#4F46E5"


def _fmt_pixmap(kind: str, color: str, accent: str = "") -> QPixmap:
    """手绘 16x16 线性风格格式图标。

    kind: bold | italic | underline | strike | highlight | color | undo | redo
    accent: 高亮/颜色图标底部色条的显示色（空则用 color）
    """
    size = 16
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    rect = QRectF(0, 0, size, size)

    if kind in ("bold", "italic", "underline", "strike"):
        # 字形图标：B / I / U / S（Figma 风格，字母即图形）
        f = QFont("Segoe UI", 11, QFont.Weight.Bold)
        if kind == "italic":
            f.setItalic(True)
        p.setFont(f)
        ch = {"bold": "B", "italic": "I", "underline": "U", "strike": "S"}[kind]
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, ch)
        if kind == "underline":
            p.drawLine(2, size - 3, size - 2, size - 3)
        elif kind == "strike":
            p.drawLine(2, size // 2, size - 2, size // 2)
    elif kind == "highlight":
        # 斜置荧光笔：笔身 + 笔尖
        p.save()
        p.translate(size / 2, size / 2)
        p.rotate(-35)
        body = QPainterPath()
        body.moveTo(-4.5, -1.5)
        body.lineTo(4.5, -1.5)
        body.lineTo(4.5, 2.5)
        body.lineTo(-4.5, 2.5)
        body.closeSubpath()
        p.drawPath(body)
        tip = QPainterPath()
        tip.moveTo(-4.5, -2.2)
        tip.lineTo(-4.5, 2.2)
        tip.lineTo(-7.6, 0.0)
        tip.closeSubpath()
        p.drawPath(tip)
        p.restore()
    elif kind == "color":
        # 字母 A + 底部色条（色条随所选颜色动态变化）
        f = QFont("Segoe UI", 11, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRectF(0, 0, size, size - 4),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "A")
        bar = QColor(accent) if accent else QColor(color)
        p.setPen(QPen(bar, 2))
        p.drawLine(2, size - 2, size - 2, size - 2)
    p.end()
    return pix


def _fmt_btn_icon(kind: str, accent: str = "") -> QIcon:
    """格式按钮图标：常态灰 / hover 与选中态 indigo（双状态图标）。"""
    icon = QIcon()
    icon.addPixmap(_fmt_pixmap(kind, ICON_COLOR, accent), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_fmt_pixmap(kind, ICON_ACTIVE, accent), QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(_fmt_pixmap(kind, ICON_ACTIVE, accent), QIcon.Mode.Selected, QIcon.State.Off)
    icon.addPixmap(_fmt_pixmap(kind, ICON_ACTIVE, accent), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def _action_icon(kind: str, color: str) -> QIcon:
    """操作按钮线性图标：save = 对勾 ✓，delete = 叉 ✕（手绘，无文件依赖）。"""
    size = 14
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    if kind == "save":
        p.drawLine(2, 8, 6, 12)
        p.drawLine(6, 12, 12, 3)
    else:
        p.drawLine(3, 3, 11, 11)
        p.drawLine(11, 3, 3, 11)
    p.end()
    return QIcon(pix)


def _ensure_arrow_png() -> str:
    """生成下拉三角箭头 PNG 供 QSS 引用，返回文件路径（正斜杠）。

    QSS 样式化 QComboBox 后原生箭头消失，Qt6 下 QSS border 三角会渲染
    成横杠、QProxyStyle 也被 QStyleSheetStyle 绕过，只能生成小 PNG
    供 QSS image 引用。存系统 temp 目录、构建时确保存在，
    不污染程序目录与 git。
    """
    path = Path(tempfile.gettempdir()) / "cstools_arrow_down.png"
    if not path.exists():
        pix = QPixmap(12, 12)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#9CA3AF"))
        tri = QPainterPath()
        tri.moveTo(2.0, 4.0)
        tri.lineTo(10.0, 4.0)
        tri.lineTo(6.0, 8.5)
        tri.closeSubpath()
        p.drawPath(tri)
        p.end()
        pix.save(str(path))
    return str(path).replace("\\", "/")


# 把箭头 PNG 路径注入 QSS（模块加载时执行一次）
FMT_COMBO_STYLE = FMT_COMBO_STYLE.replace("{ARROW}", _ensure_arrow_png())



def _color_icon(hex_color: str, size: int = 14) -> QIcon:
    """生成纯色小图标（用于格式菜单的色块）。"""
    pix = QPixmap(size, size)
    pix.fill(QColor(hex_color))
    return QIcon(pix)


class _RichTextEditor(QTextEdit):
    """富文本输入框：支持剪贴板图片粘贴 + 中文右键菜单。

    PyQt6 的 QTextEdit 默认 insertFromMimeData 对图片粘贴不生效，
    这里手动插入 QImage；右键菜单改为中文，避免默认英文菜单。
    """

    # IME 组合文本（拼音 preedit）变化：占位提示需在组合期间隐藏
    preedit_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_preedit = ""  # 当前 IME 组合文本（无组合时为空串）

    def inputMethodEvent(self, event):
        """记录 IME 组合文本并通知占位提示刷新。

        拼音组合期间 preedit 文本可见但文档内容不变，占位提示会与
        组合文本叠加显示；组合变化时发信号让占位提示同步隐藏/恢复。
        """
        self.current_preedit = event.preeditString()
        self.preedit_changed.emit()
        super().inputMethodEvent(event)

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
    """错题本：记录错题、写标题、打标签，支持粘贴截图。"""

    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, store: MistakeBookStore | None = None,
                 config: MistakeBookConfig | None = None):
        super().__init__()
        if config is None and store is None:
            # 默认使用共享实例：与全局「设置 → 错题本枚举」共用同一份
            # config/store，枚举变更才能同步到本页 UI 与内存数据
            self._config = shared_config()
            self._store = shared_store()
        else:
            self._config = config or MistakeBookConfig()
            self._store = store or MistakeBookStore(config=self._config)
        self._current_id: str | None = None  # None = 新建
        self._loading_item = False  # 加载条目时抑制保存/信号回调
        self._section_chips: dict[str, QPushButton] = {}  # 模块单选 chips
        self._reason_chips: dict[str, QPushButton] = {}  # 错因多选 chips
        self._editor: QTextEdit | None = None
        self._size_dynamic: str | None = None  # 字号下拉动态插入的实际值项
        self._category_radios: dict[str, QRadioButton] = {}  # 科目单选（枚举动态生成）
        # 搜索防抖：连续输入时延迟重建列表，避免每次击键全量刷新卡顿
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        # 工具栏下拉同步延迟定时器：QTextEdit 处理中途操作 QComboBox 会崩溃，
        # 统一延迟到事件循环空闲执行（见 _on_cursor_changed 注释）
        self._toolbar_sync_timer = QTimer(self)
        self._toolbar_sync_timer.setSingleShot(True)
        self._toolbar_sync_timer.setInterval(0)
        self._setup_ui()
        self._connect_signals()
        self._rebuild_category_radios()
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
        subtitle = QLabel("记录错题、写标题、打标签，支持粘贴截图，随时回顾")
        subtitle.setStyleSheet(SUBTLE_STYLE)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        # 设置入口（主页面级：科目/模块/错因枚举 + 富文本默认输入格式）
        self.btn_config = QPushButton("⚙ 设置")
        self.btn_config.setStyleSheet(SECONDARY_BTN)
        self.btn_config.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_config.setToolTip("自定义科目 / 模块 / 错因枚举与默认输入格式")
        header.addWidget(self.btn_config)

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

        # 筛选区：第一行 科目 / 模块 / 错因 三个下拉（模块随科目联动），
        # 第二行搜索框全宽（一行四控件时搜索框只剩约 150px，太窄）
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.combo_category = QComboBox()
        self.combo_category.addItem("全部科目", "")
        for c in self._config.categories():
            self.combo_category.addItem(c["name"], c["key"])
        self.combo_category.setStyleSheet(COMBO_STYLE)
        self.combo_category.setMinimumWidth(86)
        filters.addWidget(self.combo_category)

        self.combo_section = QComboBox()
        self.combo_section.setStyleSheet(COMBO_STYLE)
        self.combo_section.setMinimumWidth(96)
        filters.addWidget(self.combo_section)

        self.combo_reason = QComboBox()
        self.combo_reason.setStyleSheet(COMBO_STYLE)
        self.combo_reason.setMinimumWidth(96)
        filters.addWidget(self.combo_reason)
        filters.addStretch()
        layout.addLayout(filters)

        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("搜索标题、题目、错因…")
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.setStyleSheet(INPUT_STYLE)
        layout.addWidget(self.edit_search)

        # 错题表格：单列双行信息行（每行一个双行富文本 QLabel，隐藏表头）
        self.list_widget = QTableWidget(0, 1)
        self.list_widget.setStyleSheet(TABLE_STYLE)
        self.list_widget.verticalHeader().setVisible(False)
        # 双行式无表头可点击，排序固定为创建时间倒序（在 _refresh_list 内排序）
        self.list_widget.horizontalHeader().setVisible(False)
        self.list_widget.horizontalHeader().setSectionResizeMode(
            COL_INFO, QHeaderView.ResizeMode.Stretch
        )
        self.list_widget.verticalHeader().setDefaultSectionSize(46)
        self.list_widget.setShowGrid(False)
        self.list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
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

        # ④ 答案行
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

        # ① 科目（大标签，枚举可配置：单选动态生成 + 配置入口）
        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        category_row.addWidget(self._form_label("科目"))
        self.category_radios_box = QWidget()
        self.category_radios_lay = QHBoxLayout(self.category_radios_box)
        self.category_radios_lay.setContentsMargins(0, 0, 0, 0)
        self.category_radios_lay.setSpacing(4)
        category_row.addWidget(self.category_radios_box)
        category_row.addStretch()
        # 创建/更新时间（右对齐小字，与科目同一行）
        self.label_time = QLabel("")
        self.label_time.setStyleSheet(SUBTLE_STYLE)
        self.label_time.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        category_row.addWidget(self.label_time)
        lay.addLayout(category_row)

        # ② 模块（单选 chips，随科目联动）
        section_row = QHBoxLayout()
        section_row.setSpacing(8)
        section_row.addWidget(self._form_label("模块"))
        self.section_chips_box = QWidget()
        self.section_chips_lay = QHBoxLayout(self.section_chips_box)
        self.section_chips_lay.setContentsMargins(0, 0, 0, 0)
        self.section_chips_lay.setSpacing(4)
        section_row.addWidget(self.section_chips_box, stretch=1)
        lay.addLayout(section_row)

        # ③ 错因（多选 chips + 自定义输入）
        reason_row = QHBoxLayout()
        reason_row.setSpacing(8)
        reason_row.addWidget(self._form_label("错因"))
        self.reason_chips_box = QWidget()
        self.reason_chips_lay = QHBoxLayout(self.reason_chips_box)
        self.reason_chips_lay.setContentsMargins(0, 0, 0, 0)
        self.reason_chips_lay.setSpacing(4)
        reason_row.addWidget(self.reason_chips_box, stretch=1)
        lay.addLayout(reason_row)

        # ⑤ 标题（简短命名，便于列表识别；字段沿用 note 兼容旧数据）
        note_row = QHBoxLayout()
        note_row.setSpacing(8)
        note_row.addWidget(self._form_label("标题"))
        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("如：2025国考数量关系第 45 题")
        self.edit_title.setStyleSheet(INPUT_STYLE)
        note_row.addWidget(self.edit_title, stretch=1)
        lay.addLayout(note_row)

        # ⑥ 格式工具栏（只放格式工具，操作按钮独立成行更醒目）
        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(8)
        toolbar_row.addWidget(self._build_format_toolbar(), stretch=1)
        lay.addLayout(toolbar_row)

        # ⑦ 内容（富文本编辑器，占全部剩余空间 + 支持粘贴图片）
        editor_box = QWidget()
        editor_lay = QVBoxLayout(editor_box)
        editor_lay.setContentsMargins(0, 0, 0, 0)
        self._editor = _RichTextEditor()
        self._editor.setAcceptRichText(True)
        self._editor.setMinimumHeight(200)
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

        # ⑧ 操作行（保存 / 删除，右下角独立成行）
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch()
        self.btn_delete = QPushButton(_action_icon("delete", "#DC2626"), "删除")
        self.btn_delete.setStyleSheet(ACTION_DELETE_BTN)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        action_row.addWidget(self.btn_delete)
        self.btn_save = QPushButton(_action_icon("save", "#FFFFFF"), "保存")
        self.btn_save.setStyleSheet(ACTION_SAVE_BTN)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        action_row.addWidget(self.btn_save)
        lay.addLayout(action_row)
        return page

    # ---------- 富文本格式工具栏 ----------

    def _build_format_toolbar(self) -> QWidget:
        """编辑器上方格式工具栏。

        分组布局：[字体 | 字号] [B I U S] [高亮 颜色] …… [撤销 重做]，
        分隔线划分功能区；B/I/U/S 与撤销重做为图标按钮，高亮/颜色
        图标底部色条随所选颜色实时变化。
        """
        bar = QWidget()
        bar.setObjectName("formatbar")
        bar.setStyleSheet(FORMATBAR_STYLE)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(4)

        # 字体（非 editable：点击任意位置由 Qt 原生展开列表，无 popup
        # 焦点问题；展开/聚焦后直接输入字符可增量匹配字体名，如 "kai" 定位楷体。
        # 注意 QFontComboBox 默认 editable=True，必须显式关闭）
        self.combo_font = QFontComboBox()
        self.combo_font.setEditable(False)
        self.combo_font.setStyleSheet(FMT_COMBO_STYLE)
        self.combo_font.setFixedWidth(180)
        self.combo_font.setMaxVisibleItems(14)
        self.combo_font.setToolTip("字体（展开后输入可快速筛选）")
        lay.addWidget(self.combo_font)
        lay.addWidget(self._toolbar_sep())

        # 字号（非 editable：点击任意位置展开；光标处实际字号不在
        # 预设档位时，动态插入列表顶部显示）
        self.combo_size = QComboBox()
        self.combo_size.setStyleSheet(FMT_COMBO_STYLE)
        self.combo_size.addItem("默认")
        self.combo_size.addItems(
            [str(s) for s in (9, 10, 10.5, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 28, 32, 36)]
        )
        self.combo_size.setFixedWidth(64)
        self.combo_size.setToolTip("字号（pt）")
        lay.addWidget(self.combo_size)
        lay.addWidget(self._toolbar_sep())

        # B / I / U / S
        self.btn_bold = self._make_fmt_btn("bold", "加粗")
        self.btn_italic = self._make_fmt_btn("italic", "斜体")
        self.btn_underline = self._make_fmt_btn("underline", "下划线")
        self.btn_strike = self._make_fmt_btn("strike", "删除线")
        for btn in (self.btn_bold, self.btn_italic, self.btn_underline, self.btn_strike):
            lay.addWidget(btn)
        lay.addWidget(self._toolbar_sep())

        # 荧光笔高亮 / 文字颜色（图标色条随所选颜色变化）
        self.btn_highlight = QToolButton()
        self.btn_highlight.setIcon(_fmt_btn_icon("highlight"))
        self.btn_highlight.setIconSize(QSize(16, 16))
        self.btn_highlight.setToolTip("荧光笔高亮")
        self.btn_highlight.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_highlight.setMenu(self._make_color_menu(HIGHLIGHT_COLORS, self._apply_highlight, clear=True))
        self.btn_highlight.setStyleSheet(FMT_TOOLBTN_STYLE)
        self.btn_highlight.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.btn_highlight)

        self.btn_color = QToolButton()
        self.btn_color.setIcon(_fmt_btn_icon("color"))
        self.btn_color.setIconSize(QSize(16, 16))
        self.btn_color.setToolTip("文字颜色")
        self.btn_color.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_color.setMenu(self._make_color_menu(TEXT_COLORS, self._apply_text_color))
        self.btn_color.setStyleSheet(FMT_TOOLBTN_STYLE)
        self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.btn_color)

        lay.addStretch()
        self.btn_undo = self._make_text_btn("↶", "撤销")
        self.btn_redo = self._make_text_btn("↷", "重做")
        lay.addWidget(self.btn_undo)
        lay.addWidget(self.btn_redo)
        return bar

    def _make_text_btn(self, text: str, tooltip: str) -> QPushButton:
        """字符型图标按钮（撤销/重做的 ↶ ↷）。"""
        btn = QPushButton(text)
        btn.setCheckable(False)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(FMT_TEXT_BTN_STYLE)
        return btn

    def _toolbar_sep(self) -> QWidget:
        """工具栏功能区竖向分隔线。"""
        sep = QWidget()
        sep.setFixedSize(1, 18)
        sep.setStyleSheet("background: #E5E7EB; border: none;")
        return sep

    def _make_fmt_btn(self, kind: str, tooltip: str, checkable: bool = True) -> QPushButton:
        """格式工具栏图标按钮（28x28，hover/选中态图标自动变 indigo）。"""
        btn = QPushButton()
        btn.setIcon(_fmt_btn_icon(kind))
        btn.setIconSize(QSize(16, 16))
        btn.setCheckable(checkable)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(FMT_BTN_STYLE)
        return btn

    def _make_color_menu(self, colors, on_pick, clear: bool = False) -> QMenu:
        """色板菜单：每项一个色块图标，点击回调 on_pick(hex)；clear 时附「清除高亮」项。"""
        menu = QMenu(self)
        menu.setStyleSheet(FMT_MENU_STYLE)
        for name, hex_color in colors:
            act = menu.addAction(_color_icon(hex_color), name)
            act.triggered.connect(lambda _c=False, h=hex_color: on_pick(h))
        if clear:
            menu.addSeparator()
            menu.addAction("清除高亮").triggered.connect(lambda: on_pick(None))
        return menu

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
        # 科目变化需联动重建模块下拉选项
        self.combo_category.currentIndexChanged.connect(self._on_category_filter_changed)
        # 模块/错因变化只影响列表本身，下拉选项无需重建
        self.combo_section.currentIndexChanged.connect(
            lambda _: self._refresh_list(rebuild_filters=False)
        )
        self.combo_reason.currentIndexChanged.connect(
            lambda _: self._refresh_list(rebuild_filters=False)
        )
        # 搜索防抖：停止输入 200ms 后才刷新；搜索不改变下拉选项，无需重建
        self._search_timer.timeout.connect(lambda: self._refresh_list(rebuild_filters=False))
        self.edit_search.textChanged.connect(lambda _: self._search_timer.start())
        self.btn_config.clicked.connect(self._open_enum_settings)
        self._editor.textChanged.connect(self._update_editor_placeholder)
        # IME 拼音组合期间文档内容不变，需跟随组合文本变化刷新占位提示
        self._editor.preedit_changed.connect(self._update_editor_placeholder)

        # 富文本格式工具栏
        self.combo_font.currentFontChanged.connect(self._on_font_changed)
        self.combo_size.currentTextChanged.connect(self._apply_font_size)
        self.btn_bold.clicked.connect(self._toggle_bold)
        self.btn_italic.clicked.connect(self._toggle_italic)
        self.btn_underline.clicked.connect(self._toggle_underline)
        self.btn_strike.clicked.connect(self._toggle_strike)
        self.btn_undo.clicked.connect(self._editor.undo)
        self.btn_redo.clicked.connect(self._editor.redo)
        self._editor.cursorPositionChanged.connect(self._on_cursor_changed)
        self._toolbar_sync_timer.timeout.connect(self._sync_toolbar_state)
        self._editor.undoAvailable.connect(self.btn_undo.setEnabled)
        self._editor.redoAvailable.connect(self.btn_redo.setEnabled)

    # ============================================================
    #  列表
    # ============================================================

    def _refresh_list(self, rebuild_filters: bool = True):
        """按当前筛选条件（科目/模块/错因/搜索）重建列表，并更新统计与下拉选项。"""
        items = self._store.all_items()
        category = self.combo_category.currentData()
        section = self.combo_section.currentData() or ""
        reason = self.combo_reason.currentData() or ""
        keyword = self.edit_search.text().strip()

        if category:
            items = [it for it in items if it.category == category]
        if section:
            items = [it for it in items if it.section == section]
        if reason:
            items = [it for it in items if reason in it.tags]
        if keyword:
            keyword_lower = keyword.lower()
            items = [
                it for it in items
                if keyword_lower in text_preview(it.content).lower()
                or keyword_lower in it.note.lower()
                or any(keyword_lower in t.lower() for t in it.tags)
            ]

        # 双行式隐藏表头后无法点击排序，固定按创建时间倒序（最新在前）
        items.sort(key=lambda it: it.created_at, reverse=True)

        # 记住当前选中 id 与滚动位置，刷新后在 blockSignals 期间恢复，
        # 避免触发自动保存递归，也避免列表视觉跳动
        selected_id = self._current_id
        scroll_pos = self.list_widget.verticalScrollBar().value()
        self.list_widget.blockSignals(True)
        self.list_widget.setUpdatesEnabled(False)
        self.list_widget.clearContents()
        self.list_widget.setRowCount(0)
        for item in items:
            self._append_table_row(item)
        if selected_id:
            for row in range(self.list_widget.rowCount()):
                if self.list_widget.item(row, COL_INFO).data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.list_widget.setCurrentCell(row, COL_INFO)
                    break
            if self._store.get(selected_id) is None:
                # 当前条目已不在数据中（被删除/被外部清理），删除不可用
                self.btn_delete.setEnabled(False)
        self.list_widget.verticalScrollBar().setValue(scroll_pos)
        self.list_widget.setUpdatesEnabled(True)
        self.list_widget.blockSignals(False)

        # 统计
        total = self._store.count()
        uncorrected = sum(1 for it in self._store.all_items() if not it.corrected)
        self.label_count.setText(f"共 {total} 条 · 未订正 {uncorrected} 条")
        self.status_message.emit(f"错题本 - 共 {total} 条错题")

        if rebuild_filters:
            self._refresh_section_filter_options()
            self._refresh_reason_filter_options()

    def _append_table_row(self, item: MistakeItem):
        """按一条错题追加一行：双行信息布局（富文本 QLabel）。

        左侧 3px 科目色竖条标识科目；第一行：✓ 订正标记 + 标题（粗体），
        右侧短格式时间；第二行：模块 · 错因 · 内容摘要。
        """
        row = self.list_widget.rowCount()
        self.list_widget.insertRow(row)

        # 空文本 item 携带条目 id：点击整行任意位置都能定位详情
        cell = QTableWidgetItem("")
        cell.setData(Qt.ItemDataRole.UserRole, item.id)
        self.list_widget.setItem(row, COL_INFO, cell)

        label = QLabel(self._build_row_html(item))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setContentsMargins(10, 4, 10, 4)
        # 科目色竖条（背景透明：透出表格交替行/选中高亮背景）
        label.setStyleSheet(
            f"background: transparent; border-left: 3px solid "
            f"{self._config.category_color(item.category)};"
        )
        # 富文本行不拦截鼠标，点击穿透到表格完成选中
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # 悬停提示：完整标题 + 创建时间（列表内截断显示）
        tips = []
        if item.note.strip():
            tips.append(item.note.strip())
        if item.created_at:
            tips.append(f"创建时间 {item.created_at}")
        if tips:
            label.setToolTip("\n".join(tips))
        self.list_widget.setCellWidget(row, COL_INFO, label)

    def _build_row_html(self, item: MistakeItem) -> str:
        """生成双行信息行的富文本 HTML（两行一表格，宽度铺满整行）。

        科目由行首色条标识，不占文字；标题/模块/错因/摘要均为用户数据，
        插入 HTML 前统一转义；标题与摘要按列表可用宽度截断（完整内容在
        详情面板与悬停提示中），避免超长文本把固定行高（46px）撑成三行。
        """
        # 第一行：✓ 标记 + 标题（无标题置灰；长标题截断）
        title_full = item.note.strip()
        title = text_preview(title_full, 24) if title_full else "（无标题）"
        title_color = "#111827" if title_full else "#9CA3AF"
        check = '<span style="color:#16A34A;">✓ </span>' if item.corrected else ""
        time_cell = ""
        if item.created_at:
            time_cell = (
                f'<td align="right"><span style="font-size:11px; color:#9CA3AF;">'
                f'{escape(self._short_time(item.created_at))}</span></td>'
            )
        # 第二行：模块（模块色加粗，与行首科目色条呼应）· 错因 · 内容摘要
        parts = []
        if item.section:
            sec_color = self._config.section_color(item.section)
            parts.append(
                f'<span style="font-weight:600; color:{sec_color};">'
                f'{escape(item.section)}</span>'
            )
        parts.extend(escape(t) for t in item.tags)
        preview = text_preview(item.content, 24)
        if preview:
            parts.append(escape(preview))
        second_row = ""
        if parts:
            second_row = (
                f'<tr><td colspan="2"><span style="font-size:12px; color:#6B7280;">'
                f'{" · ".join(parts)}</span></td></tr>'
            )
        return (
            '<table width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td><span style="font-size:13px; font-weight:600; color:{title_color};">'
            f'{check}{escape(title)}</span></td>{time_cell}</tr>'
            f'{second_row}</table>'
        )

    @staticmethod
    def _short_time(created_at: str) -> str:
        """列表时间短格式：今年内省略年份（跨年数据显示完整日期）。"""
        if created_at.startswith(f"{datetime.now().year}-"):
            return created_at[5:]
        return created_at

    def _refresh_section_filter_options(self):
        """模块筛选下拉：随科目联动（科目=全部时显示全部模块名并集）。"""
        current = self.combo_section.currentData() or ""
        category = self.combo_category.currentData()
        names = self._config.sections(category) if category else self._config.all_section_names()
        self.combo_section.blockSignals(True)
        self.combo_section.clear()
        self.combo_section.addItem("全部模块", "")
        for name in names:
            self.combo_section.addItem(name, name)
        idx = self.combo_section.findData(current)
        self.combo_section.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_section.blockSignals(False)

    def _refresh_reason_filter_options(self):
        """错因筛选下拉：预置错因 + 数据中沉淀的自定义错因（按使用频率）。"""
        current = self.combo_reason.currentData() or ""
        names = self._config.reason_tags() + self._collect_custom_reason_pool()
        self.combo_reason.blockSignals(True)
        self.combo_reason.clear()
        self.combo_reason.addItem("全部错因", "")
        for name in names:
            self.combo_reason.addItem(name, name)
        idx = self.combo_reason.findData(current)
        self.combo_reason.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_reason.blockSignals(False)

    def _on_category_filter_changed(self):
        """筛选科目切换：模块下拉联动换选项，再按新条件刷新列表。"""
        self._refresh_section_filter_options()
        self._refresh_list(rebuild_filters=False)

    # ============================================================
    #  详情表单
    # ============================================================

    def _show_empty_state(self):
        self.detail_stack.setCurrentIndex(0)
        self.btn_delete.setEnabled(False)  # 无当前条目，删除不可用

    def _show_form(self):
        self.detail_stack.setCurrentIndex(1)

    # ---------- 枚举配置 ----------

    def _open_enum_settings(self):
        """打开设置对话框（主页面头部入口），接受后刷新所有依赖配置的 UI。

        新建状态下若编辑器为空，按新默认格式重置；已有内容则保持原样
        （默认格式只影响新建条目，不破坏正在编辑的内容）。
        """
        dlg = EnumSettingsDialog(self._config, self._store, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.refresh_enum_ui()
        if self._current_id is None and not self._editor.toPlainText().strip():
            # 新建空文档：按新默认格式重置并同步下拉（延迟到事件循环空闲，
            # 与 _new_item 一致，避免编辑器显示/QSS polish 时序覆盖格式）
            QTimer.singleShot(0, self._apply_default_format_then_sync)
        self.status_message.emit("错题本设置已更新")

    def refresh_enum_ui(self):
        """枚举变更后：左侧筛选下拉、科目单选、模块/错因 chips、列表全量刷新。"""
        # 保留当前科目/模块/错因选择（若仍存在于新枚举）
        checked_key = self._current_category_key()
        current_section = self._collect_section()
        current_reasons = self._collect_reasons()

        current_cat = self.combo_category.currentData()
        self.combo_category.blockSignals(True)
        self.combo_category.clear()
        self.combo_category.addItem("全部科目", "")
        for c in self._config.categories():
            self.combo_category.addItem(c["name"], c["key"])
        idx = self.combo_category.findData(current_cat)
        self.combo_category.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_category.blockSignals(False)

        self._rebuild_category_radios(checked_key)
        self._rebuild_section_chips(current_section)
        self._rebuild_reason_chips(current_reasons)
        self._refresh_list()

    # ---------- 富文本格式应用 ----------

    def _on_font_changed(self, font: QFont):
        fmt = QTextCharFormat()
        fmt.setFontFamily(font.family())
        self._editor.mergeCurrentCharFormat(fmt)
        self._sync_doc_font_if_empty(fmt)

    def _apply_font_size(self, text: str):
        try:
            size = float(text)
        except ValueError:
            return
        if not 4 <= size <= 100:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self._editor.mergeCurrentCharFormat(fmt)
        self._sync_doc_font_if_empty(fmt)

    def _sync_doc_font_if_empty(self, fmt: QTextCharFormat):
        """空文档时把字体族/字号同步到文档默认字体，让光标高度立即跟随字号。

        编辑器无内容时 mergeCurrentCharFormat 不会更新行高/字形渲染（实测
        caret 保持默认高度、输入第一个字符才变化），同步 document 默认字体
        后空行的行高/光标立即反映新格式。字形切换（B/I/U/S）在 toggle 中
        直接改文档默认字体，不经过本方法。
        """
        if self._editor.toPlainText():
            return
        doc = self._editor.document()
        doc_font = doc.defaultFont()
        if fmt.fontPointSize() > 0:
            doc_font.setPointSizeF(fmt.fontPointSize())
        # ⚠ FontFamily 相关 API（fontFamily()/hasProperty(FontFamily)）
        # 在 PyQt6 中触发 access violation，改用 fontFamilies() 判断：
        # 未设置字体族的格式返回空列表，不会误覆盖文档默认字体族
        families = fmt.fontFamilies() or []
        if families:
            doc_font.setFamily(families[0])
        doc.setDefaultFont(doc_font)

    def _apply_default_format(self):
        """把编辑器输入格式重置为用户配置的默认格式（新建条目时）。

        同时设置当前光标格式与文档默认字体：空文档时仅设光标格式不会
        更新行高/光标高度，必须同步 document 默认字体（同
        _sync_doc_font_if_empty 的处理）。
        """
        fmt = self._config.editor_format()
        char_fmt = QTextCharFormat()
        family = fmt.get("font_family") or ""
        if family:
            char_fmt.setFontFamily(family)
        size = float(fmt.get("font_size") or 0)
        if size > 0:
            char_fmt.setFontPointSize(size)
        char_fmt.setFontWeight(
            QFont.Weight.Bold if fmt.get("bold") else QFont.Weight.Normal
        )
        char_fmt.setFontItalic(bool(fmt.get("italic")))
        char_fmt.setFontUnderline(bool(fmt.get("underline")))
        char_fmt.setFontStrikeOut(bool(fmt.get("strikeout")))
        self._editor.setCurrentCharFormat(char_fmt)
        doc = self._editor.document()
        doc_font = doc.defaultFont()
        if family:
            doc_font.setFamily(family)
        if size > 0:
            doc_font.setPointSizeF(size)
        doc_font.setBold(char_fmt.fontWeight() > QFont.Weight.Normal)
        doc_font.setItalic(char_fmt.fontItalic())
        doc_font.setUnderline(char_fmt.fontUnderline())
        doc_font.setStrikeOut(char_fmt.fontStrikeOut())
        doc.setDefaultFont(doc_font)

    def _sync_doc_attr_if_empty(self, apply):
        """空文档时把字形改动直接写入文档默认字体并刷新按钮。

        空文档 mergeCurrentCharFormat 仅作用于光标格式，且
        QTextCharFormat.hasProperty 对「False」值失效（如
        setFontUnderline(False) 视为未设置），无法走通用同步路径；
        改为直接改 document().defaultFont()，保证按钮状态与
        实际输入格式闭环。
        """
        if self._editor.toPlainText():
            return
        doc = self._editor.document()
        doc_font = doc.defaultFont()
        apply(doc_font)
        doc.setDefaultFont(doc_font)

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        weight = self._cursor_format().fontWeight()
        fmt.setFontWeight(
            QFont.Weight.Normal if weight > QFont.Weight.Normal else QFont.Weight.Bold
        )
        self._editor.mergeCurrentCharFormat(fmt)
        self._sync_doc_attr_if_empty(
            lambda f: f.setBold(fmt.fontWeight() > QFont.Weight.Normal)
        )
        self._sync_format_buttons(self._cursor_format())

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        italic = not self._cursor_format().fontItalic()
        fmt.setFontItalic(italic)
        self._editor.mergeCurrentCharFormat(fmt)
        self._sync_doc_attr_if_empty(lambda f: f.setItalic(italic))
        self._sync_format_buttons(self._cursor_format())

    def _toggle_underline(self):
        fmt = QTextCharFormat()
        underline = not self._cursor_format().fontUnderline()
        fmt.setFontUnderline(underline)
        self._editor.mergeCurrentCharFormat(fmt)
        self._sync_doc_attr_if_empty(lambda f: f.setUnderline(underline))
        self._sync_format_buttons(self._cursor_format())

    def _toggle_strike(self):
        fmt = QTextCharFormat()
        strike = not self._cursor_format().fontStrikeOut()
        fmt.setFontStrikeOut(strike)
        self._editor.mergeCurrentCharFormat(fmt)
        self._sync_doc_attr_if_empty(lambda f: f.setStrikeOut(strike))
        self._sync_format_buttons(self._cursor_format())

    def _apply_highlight(self, hex_color: str | None):
        """荧光笔高亮（None = 清除），按钮图标色条同步更新。"""
        self.btn_highlight.setIcon(_fmt_btn_icon("highlight", accent=hex_color or ""))
        fmt = QTextCharFormat()
        if hex_color is None:
            fmt.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        else:
            fmt.setBackground(QBrush(QColor(hex_color)))
        self._editor.mergeCurrentCharFormat(fmt)

    def _apply_text_color(self, hex_color: str):
        """设置文字颜色，按钮图标色条同步更新。"""
        self.btn_color.setIcon(_fmt_btn_icon("color", accent=hex_color))
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(QColor(hex_color)))
        self._editor.mergeCurrentCharFormat(fmt)

    def _cursor_format(self) -> QTextCharFormat:
        """光标处字符格式；空文档时回落到文档默认字体。

        QTextEdit 空文档的 currentCharFormat 返回全默认空格式（字号 0、
        不加粗等），不反映 document().defaultFont()：会导致新增/删空文字
        后工具栏按钮取消选中、下拉回落「默认」。空文档时改用文档默认
        字体派生格式，使工具栏始终反映实际输入格式。
        """
        if self._editor.toPlainText():
            return self._editor.currentCharFormat()
        fmt = QTextCharFormat()
        fmt.setFont(self._editor.document().defaultFont())
        return fmt

    def _sync_format_buttons(self, fmt: QTextCharFormat):
        """按给定格式同步 B / I / U / S 按钮选中态。"""
        self.btn_bold.setChecked(fmt.fontWeight() > QFont.Weight.Normal)
        self.btn_italic.setChecked(fmt.fontItalic())
        self.btn_underline.setChecked(fmt.fontUnderline())
        self.btn_strike.setChecked(fmt.fontStrikeOut())

    def _on_cursor_changed(self):
        """光标移动时把工具栏状态同步为光标处文本的格式。

        下拉同步经 QTimer 延迟到事件循环空闲执行：既合并光标高频移动
        的重复刷新，也避开 QTextEdit 编辑处理中途操作控件的窗口。
        同步时用 blockSignals 掐断信号回写，避免误改文档格式。
        """
        if self._loading_item:
            return
        # 删空文字后 QTextEdit 会把光标格式重置为全默认空格式（字号 0、
        # 不加粗），之后输入的文字只带空格式、渲染时才回落文档默认字体，
        # 导致工具栏状态与实际渲染不符；空文档时把光标格式重新对齐到
        # 文档默认字体（幂等），保证后续输入与工具栏状态一致
        if not self._editor.toPlainText():
            fmt = QTextCharFormat()
            fmt.setFont(self._editor.document().defaultFont())
            self._editor.setCurrentCharFormat(fmt)
        self._sync_format_buttons(self._cursor_format())
        self._toolbar_sync_timer.start()

    def _sync_toolbar_state(self):
        """事件循环空闲时同步字体/字号下拉到光标处格式。"""
        fmt = self._cursor_format()
        # ⚠ 不能用 fmt.fontFamily()：PyQt6 中该方法触发 access violation
        # 崩溃（实测 fontWeight/fontItalic 均正常，仅 fontFamily 崩溃），
        # 必须走 fmt.font().family() 读取
        family = fmt.font().family()
        self.combo_font.blockSignals(True)
        if family:
            self.combo_font.setCurrentFont(QFont(family))
        self.combo_font.blockSignals(False)

        # 字号：匹配预设档位则选中；不在档位时直接显示实际值
        # （可编辑下拉），未设置字号则留空显示 placeholder「默认」
        # 字号：匹配预设档位则选中；不在档位时动态插入实际值（显示在
        # 「默认」之后），未设置字号回落到「默认」项
        size = fmt.fontPointSize()
        text = f"{size:g}" if size > 0 else ""
        self.combo_size.blockSignals(True)
        if self._size_dynamic is not None:
            idx = self.combo_size.findText(self._size_dynamic)
            if idx >= 0:
                self.combo_size.removeItem(idx)
            self._size_dynamic = None
        if text and self.combo_size.findText(text) < 0:
            self.combo_size.insertItem(1, text)
            self._size_dynamic = text
        self.combo_size.setCurrentIndex(self.combo_size.findText(text) if text else 0)
        self.combo_size.blockSignals(False)

    def _new_item(self):
        """清空表单进入新建状态（未保存的修改直接丢弃，点「保存」才入库）。"""
        self._current_id = None
        self._loading_item = True
        self._editor.clear()
        self.edit_my_answer.clear()
        self.edit_correct_answer.clear()
        self.check_corrected.setChecked(False)
        self.edit_title.clear()
        self._rebuild_category_radios()
        self._rebuild_section_chips()
        self._rebuild_reason_chips([])
        self._loading_item = False
        self._update_editor_placeholder()
        # 先清选择（触发 _on_select(None) 显示空态），随后立即切回表单页
        self.list_widget.clearSelection()
        self._show_form()
        # ⚠ 编辑器首次显示时 QSS（INPUT_STYLE 的 font-size: 13px）会重算
        # widget 字体并覆盖文档默认字体（pointSizeF 变 -1 的像素模式），
        # 且该重算在显示后的 polish 事件中处理（可能异步）；默认格式必须
        # 延迟到事件循环空闲（polish 全部处理完）再应用，随后同步工具栏下拉
        QTimer.singleShot(0, self._apply_default_format_then_sync)
        self._editor.setFocus()

    def _apply_default_format_then_sync(self):
        """事件循环空闲时应用默认输入格式并同步工具栏（见 _new_item 注释）。"""
        if self._current_id is not None:
            return  # 延迟期间已切换到已有条目，不再重置其格式
        self._loading_item = True
        self._apply_default_format()
        # 按钮/下拉同步必须读取 _cursor_format()（空文档回落文档默认字体），
        # 否则空文档 currentCharFormat 的空格式会让按钮显示未选中
        self._sync_format_buttons(self._cursor_format())
        self._sync_toolbar_state()
        self._loading_item = False

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
        self.edit_title.setText(item.note)
        self._rebuild_category_radios(item.category)
        self._loading_item = False
        self._apply_tags(item.section, item.tags)
        self._update_editor_placeholder()
        self._show_form()
        self.btn_delete.setEnabled(True)
        self.label_time.setText(
            f"创建 {item.created_at} · 更新 {item.updated_at}"
        )
        # 自动保存会刷新 updated_at 导致排序变化，这里把列表高亮对齐到当前条目
        self._loading_item = True
        self.list_widget.blockSignals(True)
        for row in range(self.list_widget.rowCount()):
            if self.list_widget.item(row, COL_INFO).data(Qt.ItemDataRole.UserRole) == item_id:
                self.list_widget.setCurrentCell(row, COL_INFO)
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
        preset = self._config.sections(self._current_category_key())
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
        preset = set(self._config.reason_tags())
        for it in self._store.all_items():
            for t in it.tags:
                if t not in preset:
                    counter[t] += 1
        return [name for name, _ in counter.most_common(limit)]

    def _rebuild_reason_chips(self, checked_names: list[str]):
        """重建错因 chips：预置 + 用户自定义建议（按频率），仅勾选 checked_names。

        自定义错因一旦被用过就会沉淀为建议，新建条目时点选即可复用。
        """
        self._clear_layout(self.reason_chips_lay)
        self._reason_chips = {}
        suggestions = self._collect_custom_reason_pool()
        for name in self._config.reason_tags() + suggestions:
            btn = self._make_chip(name, name in checked_names)
            self.reason_chips_lay.addWidget(btn)
            self._reason_chips[name] = btn
        for name in checked_names:
            if name not in self._reason_chips:  # 不在预置/建议池（如已从数据中消失）
                btn = self._make_chip(name, True)
                self.reason_chips_lay.insertWidget(self.reason_chips_lay.count() - 1, btn)
                self._reason_chips[name] = btn
        self.reason_chips_lay.addStretch()

    def _on_category_changed(self):
        """科目切换：模块 chips 换预置，错因 chips 保持当前选中。"""
        self._rebuild_section_chips()
        self._rebuild_reason_chips(self._collect_reasons())

    # ---------- 科目单选（枚举动态生成） ----------

    def _rebuild_category_radios(self, checked_key: str = ""):
        """按配置重建科目单选（QRadioButton 同父级自动互斥）。"""
        self._clear_layout(self.category_radios_lay)
        self._category_radios = {}
        cats = self._config.categories()
        if not cats:
            return
        if not checked_key or checked_key not in self._config.category_keys():
            checked_key = cats[0]["key"]
        for c in cats:
            btn = QRadioButton(c["name"])
            btn.setStyleSheet(RADIO_STYLE)
            btn.blockSignals(True)  # 重建期间抑制 toggled 联动
            self.category_radios_lay.addWidget(btn)
            btn.setChecked(c["key"] == checked_key)
            btn.blockSignals(False)
            btn.toggled.connect(
                lambda on, b=btn: self._on_category_changed() if on else None
            )
            self._category_radios[c["key"]] = btn

    def _collect_category(self) -> str:
        for key, btn in self._category_radios.items():
            if btn.isChecked():
                return key
        return ""

    def _current_category_key(self) -> str:
        key = self._collect_category()
        if not key:
            keys = self._config.category_keys()
            if keys:
                return keys[0]
        return key

    def _collect_section(self) -> str:
        for name, btn in self._section_chips.items():
            if btn.isChecked():
                return name
        return ""

    def _collect_reasons(self) -> list[str]:
        return [name for name, btn in self._reason_chips.items() if btn.isChecked()]

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
            category=self._current_category_key(),
            section=self._collect_section(),
            tags=self._collect_reasons(),
            my_answer=self.edit_my_answer.text().strip(),
            correct_answer=self.edit_correct_answer.text().strip(),
            corrected=self.check_corrected.isChecked(),
            note=self.edit_title.text().strip(),
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
        """大输入框空内容时显示提示浮层。

        只要内容非空（包括空格/换行等纯空白，以及 IME 拼音组合文本）
        就隐藏提示；只有整个富文本框内容为空时才显示。
        """
        hidden = bool(self._editor.toPlainText()) or bool(self._editor.current_preedit)
        self._editor_placeholder.setVisible(not hidden)
