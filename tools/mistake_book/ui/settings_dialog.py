"""错题本设置对话框：科目 / 模块 / 错因 三维枚举 + 富文本默认输入格式。

- 变更立即写入配置并落盘；
- 科目与模块支持自定义颜色（列表项前色块 + 「颜色」按钮），
  颜色用于错题本左侧列表的科目色条与模块文字着色；
- 模块与错因的重命名/删除会同步迁移存量错题（改 section / tags 字段），
  删除前展示引用计数并二次确认；
- 科目删除仅在该科目下无错题时允许（存量数据无安全落点）；
- 「默认格式」页配置新建错题时编辑器的输入格式（字体/字号/字形）。
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFontComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tools.mistake_book.core.mistake_book import (
    DEFAULT_EDITOR_FORMAT,
    MistakeBookConfig,
    MistakeBookStore,
)

DIALOG_QSS = (
    "QDialog { background-color: #FFFFFF; }"
    "QTabWidget::pane { border: 1px solid #E5E7EB; border-radius: 8px; top: -1px; }"
    "QTabBar::tab { background: transparent; color: #6B7280;"
    "  border: none; padding: 7px 18px; font-size: 13px; font-weight: 600; }"
    "QTabBar::tab:selected { color: #4F46E5; border-bottom: 2px solid #4F46E5; }"
    "QListWidget { background-color: #FFFFFF; border: 1px solid #E5E7EB;"
    "  border-radius: 8px; font-size: 13px; color: #1F2937; outline: none; }"
    "QListWidget::item { padding: 6px 10px; border-bottom: 1px solid #F3F4F6; }"
    "QListWidget::item:selected { background-color: #EEF2FF; color: #4F46E5; }"
    "QComboBox, QFontComboBox { background-color: #FFFFFF; border: 1px solid #E5E7EB;"
    "  border-radius: 7px; padding: 3px 8px; font-size: 12px; color: #374151;"
    "  min-height: 24px; }"
    "QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {"
    "  background-color: #FFFFFF; border: 1px solid #E5E7EB;"
    "  selection-background-color: #EEF2FF; selection-color: #4F46E5; }"
    "QCheckBox { font-size: 13px; color: #374151; background: transparent;"
    "  border: none; padding: 2px 0; }"
    "QCheckBox::indicator { width: 15px; height: 15px; }"
    "QPushButton#op { background-color: #FFFFFF; color: #4F46E5;"
    "  border: 1px solid #E0E7FF; border-radius: 7px; padding: 4px 12px;"
    "  font-size: 12px; font-weight: 600; }"
    "QPushButton#op:hover { background-color: #EEF2FF; }"
    "QPushButton#danger { background-color: #FFFFFF; color: #DC2626;"
    "  border: 1px solid #FECACA; border-radius: 7px; padding: 4px 12px;"
    "  font-size: 12px; font-weight: 600; }"
    "QPushButton#danger:hover { background-color: #FEF2F2; }"
    "QPushButton#primary { background-color: #4F46E5; color: #FFFFFF;"
    "  border: none; border-radius: 7px; padding: 5px 22px;"
    "  font-size: 12px; font-weight: 600; }"
    "QPushButton#primary:hover { background-color: #4338CA; }"
    "QLabel { background: transparent; }"
)

SUBTLE_LABEL = "font-size: 12px; color: #9CA3AF; background: transparent; border: none;"


def _swatch_icon(hex_color: str) -> QIcon:
    """纯色小块图标（枚举列表项前的颜色指示）。"""
    pix = QPixmap(14, 14)
    pix.fill(QColor(hex_color))
    return QIcon(pix)


class EnumSettingsDialog(QDialog):
    """错题本设置对话框：枚举三维 + 富文本默认输入格式。"""

    def __init__(self, config: MistakeBookConfig, store: MistakeBookStore,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._config = config
        self._store = store
        self.setWindowTitle("错题本设置")
        self.setStyleSheet(DIALOG_QSS)
        self.resize(480, 520)
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        tip = QLabel("自定义枚举值与富文本默认格式；重命名 / 删除会自动同步已录的错题")
        tip.setStyleSheet(SUBTLE_LABEL)
        root.addWidget(tip)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_category_page(), "科目")
        self.tabs.addTab(self._build_section_page(), "模块")
        self.tabs.addTab(self._build_reason_page(), "错因")
        self.tabs.addTab(self._build_format_page(), "默认格式")
        root.addWidget(self.tabs, stretch=1)

        row = QHBoxLayout()
        row.addStretch()
        btn_done = QPushButton("完成")
        btn_done.setObjectName("primary")
        btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_done.clicked.connect(self.accept)
        row.addWidget(btn_done)
        root.addLayout(row)

    # ---------- 通用骨架 ----------

    @staticmethod
    def _page_scaffold(extra: QWidget | None = None, with_color: bool = False):
        """页骨架：可选顶部控件 + 列表 + 操作按钮列（可选颜色按钮）。

        返回 (page, lst, btn_add, btn_rename, btn_del, btn_color)，
        with_color=False 时 btn_color 为 None。
        """
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 10, 4, 4)
        lay.setSpacing(8)
        if extra is not None:
            lay.addWidget(extra)
        body = QHBoxLayout()
        body.setSpacing(8)
        lst = QListWidget()
        body.addWidget(lst, stretch=1)
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        btn_add = QPushButton("＋ 添加")
        btn_rename = QPushButton("✎ 重命名")
        btn_del = QPushButton("✕ 删除")
        btn_add.setObjectName("op")
        btn_rename.setObjectName("op")
        btn_del.setObjectName("danger")
        for b in (btn_add, btn_rename, btn_del):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_col.addWidget(b)
        btn_color = None
        if with_color:
            btn_color = QPushButton("🎨 颜色")
            btn_color.setObjectName("op")
            btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_col.addWidget(btn_color)
        btn_col.addStretch()
        body.addLayout(btn_col)
        lay.addLayout(body)
        return page, lst, btn_add, btn_rename, btn_del, btn_color

    def _ask_name(self, title: str, label: str, current: str = "") -> str:
        name, ok = QInputDialog.getText(self, title, label, text=current)
        return name.strip() if ok else ""

    # ---------- 科目页 ----------

    def _build_category_page(self) -> QWidget:
        page, self._cat_list, add, rename, dlt, color = self._page_scaffold(with_color=True)
        self._reload_categories()
        add.clicked.connect(self._add_category)
        rename.clicked.connect(self._rename_category)
        dlt.clicked.connect(self._del_category)
        color.clicked.connect(self._edit_category_color)
        return page

    def _reload_categories(self):
        self._cat_list.clear()
        for c in self._config.categories():
            item = QListWidgetItem(f"{c['name']}（{c['key']}）")
            item.setIcon(_swatch_icon(self._config.category_color(c["key"])))
            self._cat_list.addItem(item)

    def _add_category(self):
        name = self._ask_name("添加科目", "科目名称：")
        if not name:
            return
        self._config.add_category(name)
        self._reload_categories()

    def _rename_category(self):
        row = self._cat_list.currentRow()
        if row < 0:
            return
        c = self._config.categories()[row]
        name = self._ask_name("重命名科目", "科目名称：", c["name"])
        if not name or name == c["name"]:
            return
        self._config.rename_category(c["key"], name)
        self._reload_categories()

    def _edit_category_color(self):
        row = self._cat_list.currentRow()
        if row < 0:
            return
        c = self._config.categories()[row]
        chosen = QColorDialog.getColor(
            QColor(self._config.category_color(c["key"])), self,
            f"选择科目「{c['name']}」的颜色",
        )
        if not chosen.isValid():
            return
        self._config.set_category_color(c["key"], chosen.name())
        self._reload_categories()

    def _del_category(self):
        row = self._cat_list.currentRow()
        if row < 0:
            return
        c = self._config.categories()[row]
        count = self._store.count_category(c["key"])
        if count > 0:
            QMessageBox.warning(
                self, "无法删除",
                f"科目「{c['name']}」下还有 {count} 条错题，\n请先转移或删除这些错题。",
            )
            return
        if QMessageBox.question(self, "删除科目", f"确定删除科目「{c['name']}」吗？") \
                != QMessageBox.StandardButton.Yes:
            return
        self._config.remove_category(c["key"])
        self._reload_categories()

    # ---------- 模块页 ----------

    def _build_section_page(self) -> QWidget:
        extra = QWidget()
        extra_lay = QHBoxLayout(extra)
        extra_lay.setContentsMargins(0, 0, 0, 0)
        label = QLabel("科目：")
        label.setStyleSheet("font-size: 13px; color: #374151;")
        extra_lay.addWidget(label)
        self._sec_combo = QComboBox()
        for c in self._config.categories():
            self._sec_combo.addItem(c["name"], c["key"])
        self._sec_combo.currentIndexChanged.connect(lambda _: self._reload_sections())
        extra_lay.addWidget(self._sec_combo)
        extra_lay.addStretch()

        page, self._sec_list, add, rename, dlt, color = self._page_scaffold(extra, with_color=True)
        self._reload_sections()
        add.clicked.connect(self._add_section)
        rename.clicked.connect(self._rename_section)
        dlt.clicked.connect(self._del_section)
        color.clicked.connect(self._edit_section_color)
        return page

    def _reload_sections(self):
        self._sec_list.clear()
        for name in self._config.sections(self._sec_combo.currentData() or ""):
            item = QListWidgetItem(name)
            item.setIcon(_swatch_icon(self._config.section_color(name)))
            self._sec_list.addItem(item)

    def _add_section(self):
        name = self._ask_name("添加模块", "模块名称：")
        if not name:
            return
        self._config.add_section(self._sec_combo.currentData() or "", name)
        self._reload_sections()

    def _rename_section(self):
        row = self._sec_list.currentRow()
        if row < 0:
            return
        cat = self._sec_combo.currentData() or ""
        old = self._config.sections(cat)[row]
        name = self._ask_name("重命名模块", "模块名称：", old)
        if not name or name == old:
            return
        self._config.rename_section(old, name)
        self._store.rename_section(old, name)
        self._reload_sections()

    def _edit_section_color(self):
        row = self._sec_list.currentRow()
        if row < 0:
            return
        cat = self._sec_combo.currentData() or ""
        name = self._config.sections(cat)[row]
        chosen = QColorDialog.getColor(
            QColor(self._config.section_color(name)), self,
            f"选择模块「{name}」的颜色",
        )
        if not chosen.isValid():
            return
        self._config.set_section_color(name, chosen.name())
        self._reload_sections()

    def _del_section(self):
        row = self._sec_list.currentRow()
        if row < 0:
            return
        cat = self._sec_combo.currentData() or ""
        name = self._config.sections(cat)[row]
        count = self._store.count_section(name)
        msg = f"确定删除模块「{name}」吗？"
        if count:
            msg += f"\n该模块下有 {count} 条错题，删除后它们的模块信息将被清空。"
        if QMessageBox.question(self, "删除模块", msg) != QMessageBox.StandardButton.Yes:
            return
        self._config.remove_section(cat, name)
        self._store.clear_section(name)
        self._reload_sections()

    # ---------- 错因页 ----------

    def _build_reason_page(self) -> QWidget:
        page, self._reason_list, add, rename, dlt, _ = self._page_scaffold()
        self._reload_reasons()
        add.clicked.connect(self._add_reason)
        rename.clicked.connect(self._rename_reason)
        dlt.clicked.connect(self._del_reason)
        return page

    def _reload_reasons(self):
        self._reason_list.clear()
        self._reason_list.addItems(self._config.reason_tags())

    def _add_reason(self):
        name = self._ask_name("添加错因", "错因名称：")
        if not name:
            return
        self._config.add_reason_tag(name)
        self._reload_reasons()

    def _rename_reason(self):
        row = self._reason_list.currentRow()
        if row < 0:
            return
        old = self._config.reason_tags()[row]
        name = self._ask_name("重命名错因", "错因名称：", old)
        if not name or name == old:
            return
        self._config.rename_reason_tag(old, name)
        self._store.rename_tag(old, name)
        self._reload_reasons()

    def _del_reason(self):
        row = self._reason_list.currentRow()
        if row < 0:
            return
        name = self._config.reason_tags()[row]
        count = self._store.count_tag(name)
        msg = f"确定删除错因「{name}」吗？"
        if count:
            msg += f"\n有 {count} 条错题使用该错因，删除后这些标签将被移除。"
        if QMessageBox.question(self, "删除错因", msg) != QMessageBox.StandardButton.Yes:
            return
        self._config.remove_reason_tag(name)
        self._store.remove_tag(name)
        self._reload_reasons()

    # ---------- 默认格式页 ----------

    # 字号档位与编辑器工具栏一致（「默认」+ 9~36pt）
    _FMT_SIZES = [9, 10, 10.5, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 28, 32, 36]

    def _build_format_page(self) -> QWidget:
        """富文本默认输入格式页：字体 / 字号 / 字形 + 实时预览。

        变更立即落盘（与枚举页一致）；「恢复默认」还原出厂值。
        """
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 10, 4, 4)
        lay.setSpacing(10)

        # 字体 + 字号（第 0 项「默认（系统）」= 存空串 = 跟随系统默认）
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._fmt_field_label("字体"))
        self._fmt_font = QFontComboBox()
        self._fmt_font.setEditable(False)
        self._fmt_font.setMaxVisibleItems(14)
        self._fmt_font.insertItem(0, "默认（系统）")
        row.addWidget(self._fmt_font, stretch=1)
        row.addWidget(self._fmt_field_label("字号"))
        self._fmt_size = QComboBox()
        self._fmt_size.addItem("默认", 0.0)
        for s in self._FMT_SIZES:
            self._fmt_size.addItem(f"{s:g}", float(s))
        row.addWidget(self._fmt_size)
        lay.addLayout(row)

        # 字形
        shape_row = QHBoxLayout()
        shape_row.setSpacing(14)
        self._fmt_bold = QCheckBox("加粗")
        self._fmt_italic = QCheckBox("斜体")
        self._fmt_underline = QCheckBox("下划线")
        self._fmt_strike = QCheckBox("删除线")
        for cb in (self._fmt_bold, self._fmt_italic, self._fmt_underline, self._fmt_strike):
            shape_row.addWidget(cb)
        shape_row.addStretch()
        lay.addLayout(shape_row)

        # 实时预览
        tip = QLabel("效果预览")
        tip.setStyleSheet("font-size: 12px; font-weight: 600; color: #6B7280;")
        lay.addWidget(tip)
        self._fmt_preview = QLabel("示例文字 Aa 公考错题")
        self._fmt_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fmt_preview.setMinimumHeight(64)
        self._fmt_preview.setStyleSheet(
            "background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px;"
        )
        lay.addWidget(self._fmt_preview)
        # 格式摘要：明确显示当前字体/字号/字形，避免西文字体对中文回退
        # 导致的「看起来没变」歧义
        self._fmt_summary = QLabel("")
        self._fmt_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fmt_summary.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent;"
        )
        lay.addWidget(self._fmt_summary)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_reset = QPushButton("恢复默认")
        btn_reset.setObjectName("op")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._reset_format)
        btn_row.addWidget(btn_reset)
        lay.addLayout(btn_row)

        lay.addStretch()

        self._fmt_font.currentFontChanged.connect(self._on_format_changed)
        self._fmt_size.currentIndexChanged.connect(self._on_format_changed)
        for cb in (self._fmt_bold, self._fmt_italic, self._fmt_underline, self._fmt_strike):
            cb.toggled.connect(self._on_format_changed)
        self._load_format_controls()
        return page

    def _fmt_field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 13px; color: #374151;")
        return label

    def _load_format_controls(self):
        """从配置载入当前默认格式（加载期间抑制信号，避免误存）。"""
        fmt = self._config.editor_format()
        family = fmt.get("font_family") or ""
        self._fmt_font.blockSignals(True)
        if family:
            # setCurrentFont 按字体族匹配（与编辑器工具栏同步写法一致）
            self._fmt_font.setCurrentFont(QFont(family))
        else:
            self._fmt_font.setCurrentIndex(0)
        self._fmt_font.blockSignals(False)
        self._fmt_size.blockSignals(True)
        idx = self._fmt_size.findData(float(fmt.get("font_size") or 0))
        self._fmt_size.setCurrentIndex(idx if idx >= 0 else 0)
        self._fmt_size.blockSignals(False)
        for cb, key in ((self._fmt_bold, "bold"), (self._fmt_italic, "italic"),
                        (self._fmt_underline, "underline"), (self._fmt_strike, "strikeout")):
            cb.blockSignals(True)
            cb.setChecked(bool(fmt.get(key, False)))
            cb.blockSignals(False)
        self._refresh_format_preview()

    def _collect_format(self) -> dict:
        """从控件收集当前选择（供落盘）。"""
        family = "" if self._fmt_font.currentIndex() == 0 \
            else self._fmt_font.currentFont().family()
        return {
            "font_family": family,
            "font_size": float(self._fmt_size.currentData() or 0),
            "bold": self._fmt_bold.isChecked(),
            "italic": self._fmt_italic.isChecked(),
            "underline": self._fmt_underline.isChecked(),
            "strikeout": self._fmt_strike.isChecked(),
        }

    def _on_format_changed(self, *_):
        """任一格式控件变化：立即落盘并刷新预览。"""
        self._config.set_editor_format(self._collect_format())
        self._refresh_format_preview()

    def _refresh_format_preview(self):
        """预览标签按当前所选格式渲染示例文字，并刷新格式摘要。

        ⚠ 字体/字号必须写进预览控件自身的 styleSheet：应用级 QSS
        （app.qss 的 `QLabel { font-size: 13px }`、`QWidget { font-family }`）
        的字体属性优先级高于 setFont，直接 setFont 的字体/字号会被全局
        样式覆盖而「看起来没变」（加粗/斜体/下划线因 QSS 未设置而不受影响），
        写入控件自身 styleSheet（优先级最高）才能实时生效。
        """
        fmt = self._collect_format()
        # 「默认（系统）」= 应用全局字体（Microsoft YaHei）/ 13px，与全局一致
        family = fmt["font_family"] or "Microsoft YaHei"
        size_pt = fmt["font_size"] if fmt["font_size"] > 0 else 13
        css = (
            "background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px;"
            f' font-family: "{family}";'
            f" font-size: {size_pt:g}pt;"
        )
        if fmt["bold"]:
            css += " font-weight: bold;"
        if fmt["italic"]:
            css += " font-style: italic;"
        if fmt["underline"] and fmt["strikeout"]:
            css += " text-decoration: underline line-through;"
        elif fmt["underline"]:
            css += " text-decoration: underline;"
        elif fmt["strikeout"]:
            css += " text-decoration: line-through;"
        self._fmt_preview.setStyleSheet(css)

        parts = [fmt["font_family"] or "系统默认"]
        parts.append(f"{fmt['font_size']:g}pt" if fmt["font_size"] > 0 else "默认字号")
        for name, on in (("加粗", fmt["bold"]), ("斜体", fmt["italic"]),
                         ("下划线", fmt["underline"]), ("删除线", fmt["strikeout"])):
            if on:
                parts.append(name)
        self._fmt_summary.setText(" · ".join(parts))

    def _reset_format(self):
        """恢复出厂默认格式并落盘。"""
        self._config.set_editor_format(dict(DEFAULT_EDITOR_FORMAT))
        self._load_format_controls()
