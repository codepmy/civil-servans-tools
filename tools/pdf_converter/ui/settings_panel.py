"""右侧设置面板: 调整排版参数(字体/字号/行距/边距等)。"""

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QDoubleSpinBox, QCheckBox, QPushButton, QGroupBox,
    QScrollArea, QRadioButton, QSpinBox,
)
from PyQt6.QtCore import pyqtSignal, QEvent, QObject, Qt


# ============================================================
# 滚轮事件过滤器: 阻止滚轮修改输入控件的值，同时保留面板滚动
# ============================================================
class _WheelBlockFilter(QObject):
    """拦截 QSpinBox/QComboBox 的滚轮事件。

    这两类控件默认会“吃掉”滚轮（数字框改值、下拉框切换选项），
    但直接吞掉会导致光标停在输入框上时整个设置面板滚不动。
    这里改为把滚轮转发给外层 QScrollArea：值不变，面板照常滚动。
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            parent = obj.parent()
            while parent is not None and not isinstance(parent, QScrollArea):
                parent = parent.parent()
            if parent is not None:
                QApplication.sendEvent(parent.viewport(), event)
            return True
        return super().eventFilter(obj, event)

_wheel_blocker = _WheelBlockFilter()

# 控件基础样式
SPINBOX_STYLE = "QSpinBox, QDoubleSpinBox { padding: 5px 10px; font-size: 13px; min-height: 28px; }"
COMBOBOX_STYLE = "QComboBox { padding: 5px 10px; font-size: 13px; min-height: 28px; }"

# 预设参数
PRESET_GUOKAO = {
    "body_font": "FangSong", "body_size": 14.0,
    "num_font": "FangSong", "opt_font": "FangSong",
    "opt_size": 14.0, "line_spacing": 1.2,
    "page_size": "B5",
}
PRESET_LIANKAO = {
    "body_font": "FangSong", "body_size": 12.0,
    "num_font": "FangSong", "opt_font": "FangSong",
    "opt_size": 12.0, "line_spacing": 1.0,
    "page_size": "B5",
}

PAPER_SIZES = ["A4", "B5", "A3", "B4", "16开"]

# 「行测模块删除」勾选项: (传给流水线的模块名, 界面文字)
# 界面文字统一取四字简称，才能排成整齐的两列卡片；完整名称放在 tooltip 里。
DROP_SECTION_ITEMS = [
    ("政治理论", "政治理论"),
    ("常识判断", "常识判断"),
    ("言语理解与表达", "言语理解"),
    ("数量关系", "数量关系"),
    ("判断推理", "判断推理"),
    ("资料分析", "资料分析"),
]

# 模块卡片样式: 白底圆角卡片，悬停浅灰，勾选后整卡变 Indigo 浅底
DROP_CHECK_STYLE = """
QCheckBox#drop-section {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 8px 8px;
    spacing: 6px;
    font-size: 12px;
    color: #374151;
}
QCheckBox#drop-section:hover {
    background-color: #F9FAFB;
    border-color: #C7D2FE;
}
QCheckBox#drop-section:checked {
    background-color: #EEF2FF;
    border-color: #A5B4FC;
    color: #4338CA;
    font-weight: 600;
}
"""

# 「清空所选」: 描边小按钮，避免原来纯文字链接过于不起眼
DROP_CLEAR_STYLE = """
QPushButton#drop-clear {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    color: #4B5563;
    min-height: 22px;
}
QPushButton#drop-clear:hover {
    background-color: #FEF2F2;
    border-color: #FCA5A5;
    color: #B91C1C;
}
QPushButton#drop-clear:pressed {
    background-color: #FEE2E2;
    border-color: #FCA5A5;
}
"""

# 面向行测/申论密集排版的默认边距，优先扩大正文可用宽度。
PAPER_MARGIN_PRESETS = {
    "A3": {"top": 20, "bottom": 16, "left": 18, "right": 16},
    "A4": {"top": 16, "bottom": 14, "left": 15, "right": 13},
    "B4": {"top": 18, "bottom": 15, "left": 16, "right": 14},
    "B5": {"top": 12, "bottom": 10, "left": 10, "right": 8},
    "16开": {"top": 13, "bottom": 11, "left": 11, "right": 9},
}


class SettingsPanel(QWidget):
    config_changed = pyqtSignal(dict)
    convert_now = pyqtSignal()

    def __init__(self, fonts: list[str] = None):
        super().__init__()
        self._fonts = fonts or ["SimSun", "SimHei", "KaiTi", "FangSong"]
        self._setup_ui()
        self._load_defaults()

    # ============================================================
    # UI构建
    # ============================================================
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("⚙ 排版设置")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #111827; padding: 4px 0 6px 0;")
        main_layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # === 考试类型 ===
        grp_type = QGroupBox("考试类型")
        t_layout = QVBoxLayout(grp_type)
        self.combo_template = self._make_combo(["行测 (行政职业能力测验)", "申论"])
        self.combo_template.currentIndexChanged.connect(self._on_config_changed)
        t_layout.addWidget(self.combo_template)
        layout.addWidget(grp_type)

        # === 行测模块删除 ===
        grp_drop = QGroupBox("行测模块删除")
        dp_layout = QVBoxLayout(grp_drop)
        dp_layout.setSpacing(6)

        dp_hint = QLabel("✂ 勾选后整段不输出（标题、题目、图表），模块序号自动递补")
        dp_hint.setWordWrap(True)
        dp_hint.setStyleSheet("color: #6B7280; font-size: 11px;")
        dp_layout.addWidget(dp_hint)

        dp_grid = QGridLayout()
        dp_grid.setHorizontalSpacing(6)
        dp_grid.setVerticalSpacing(6)
        dp_grid.setColumnStretch(0, 1)
        dp_grid.setColumnStretch(1, 1)
        self._drop_checks: dict[str, QCheckBox] = {}
        for index, (key, label) in enumerate(DROP_SECTION_ITEMS):
            chk = QCheckBox(label)
            chk.setObjectName("drop-section")
            chk.setStyleSheet(DROP_CHECK_STYLE)
            chk.setToolTip(
                f"转换时删除「{key}」模块；合并式标题（如「政治理论/常识判断」）"
                "勾选任一即整段删除"
            )
            chk.toggled.connect(self._on_config_changed)
            dp_grid.addWidget(chk, index // 2, index % 2)
            self._drop_checks[key] = chk
        dp_layout.addLayout(dp_grid)

        # 删除后的题号处理: 默认保留原卷编号，便于按原题号对答案
        dp_number_label = QLabel("删除后的题号:")
        dp_number_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        dp_layout.addWidget(dp_number_label)

        self.radio_keep_numbers = QRadioButton("保持原卷题号（推荐）")
        self.radio_keep_numbers.setToolTip(
            "删除模块后，剩余题目沿用原卷题号，便于按原题号对答案、回看解析"
        )
        self.radio_keep_numbers.setChecked(True)
        self.radio_keep_numbers.toggled.connect(self._on_config_changed)
        dp_layout.addWidget(self.radio_keep_numbers)

        self.radio_renumber = QRadioButton("从第 1 题连续递补")
        self.radio_renumber.setToolTip("删除模块后，剩余题目从第 1 题重新连续编号")
        self.radio_renumber.toggled.connect(self._on_config_changed)
        dp_layout.addWidget(self.radio_renumber)

        # 底部状态行: 已选数量提示 + 一键清空
        self._drop_footer = QWidget()
        dp_footer_layout = QHBoxLayout(self._drop_footer)
        dp_footer_layout.setContentsMargins(0, 0, 0, 0)
        dp_footer_layout.setSpacing(4)
        self._drop_summary = QLabel()
        self._drop_summary.setWordWrap(True)
        self._drop_summary.setStyleSheet(
            "color: #B45309; font-size: 11px; font-weight: 600;"
        )
        dp_footer_layout.addWidget(self._drop_summary, 1)
        self._btn_clear_drop = QPushButton("清空所选")
        self._btn_clear_drop.setObjectName("drop-clear")
        self._btn_clear_drop.setStyleSheet(DROP_CLEAR_STYLE)
        self._btn_clear_drop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_clear_drop.clicked.connect(self._clear_drop_sections)
        dp_footer_layout.addWidget(self._btn_clear_drop)
        self._drop_footer.setVisible(False)
        dp_layout.addWidget(self._drop_footer)

        layout.addWidget(grp_drop)
        self._grp_drop = grp_drop

        # === 快速预设 ===
        grp_preset = QGroupBox("快速预设")
        p_layout = QVBoxLayout(grp_preset)
        self.btn_guokao = QPushButton("🏛 国考真题字体设置")
        self.btn_guokao.setToolTip("仿宋 四号(14pt) 行距1.2 B5纸")
        self.btn_guokao.clicked.connect(self._apply_guokao)
        self.btn_guokao.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #E5E7EB; "
            "border-left: 3px solid #D97706; border-radius: 6px; padding: 8px 10px; "
            "font-weight: 600; font-size: 12px; color: #374151; }"
            "QPushButton:hover { background-color: #FFFBEB; border-color: #D97706; "
            "border-left: 3px solid #D97706; }"
        )
        p_layout.addWidget(self.btn_guokao)

        self.btn_liankao = QPushButton("📝 联考真题字体设置")
        self.btn_liankao.setToolTip("仿宋 小四号(12pt) 行距1.0 B5纸")
        self.btn_liankao.clicked.connect(self._apply_liankao)
        self.btn_liankao.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #E5E7EB; "
            "border-left: 3px solid #059669; border-radius: 6px; padding: 8px 10px; "
            "font-weight: 600; font-size: 12px; color: #374151; }"
            "QPushButton:hover { background-color: #ECFDF5; border-color: #059669; "
            "border-left: 3px solid #059669; }"
        )
        p_layout.addWidget(self.btn_liankao)
        layout.addWidget(grp_preset)

        # === 纸张大小 ===
        grp_paper = QGroupBox("纸张大小")
        a_layout = QVBoxLayout(grp_paper)
        self.combo_paper = self._make_combo(PAPER_SIZES)
        self.combo_paper.setCurrentText("A4")
        self.combo_paper.currentTextChanged.connect(self._on_paper_changed)
        a_layout.addWidget(self.combo_paper)
        layout.addWidget(grp_paper)

        # === 字体 ===
        grp_fonts = QGroupBox("字体")
        f_layout = QVBoxLayout(grp_fonts)

        f_layout.addWidget(QLabel("正文/题干:"))
        self.combo_body_font = self._make_combo(self._fonts)
        self.combo_body_font.currentTextChanged.connect(self._on_config_changed)
        f_layout.addWidget(self.combo_body_font)

        self.spin_body_size = self._make_dspin(7, 20, 10.5, " pt")
        f_layout.addWidget(self.spin_body_size)

        f_layout.addWidget(QLabel("题号:"))
        self.combo_num_font = self._make_combo(self._fonts)
        self.combo_num_font.currentTextChanged.connect(self._on_config_changed)
        f_layout.addWidget(self.combo_num_font)

        f_layout.addWidget(QLabel("选项:"))
        self.combo_opt_font = self._make_combo(self._fonts)
        self.combo_opt_font.currentTextChanged.connect(self._on_config_changed)
        f_layout.addWidget(self.combo_opt_font)

        self.spin_opt_size = self._make_dspin(7, 20, 10.5, " pt")
        f_layout.addWidget(self.spin_opt_size)

        f_layout.addWidget(QLabel("页眉:"))
        self.combo_header_font = self._make_combo(self._fonts)
        self.combo_header_font.currentTextChanged.connect(self._on_config_changed)
        f_layout.addWidget(self.combo_header_font)

        self.spin_header_size = self._make_dspin(8, 24, 12.0, " pt")
        f_layout.addWidget(self.spin_header_size)

        layout.addWidget(grp_fonts)

        # === 间距 ===
        grp_spacing = QGroupBox("间距与布局")
        s_layout = QVBoxLayout(grp_spacing)

        s_layout.addWidget(QLabel("行距倍数:"))
        self.spin_line_spacing = self._make_dspin(0.8, 3.0, 1.5, " 倍", 0.1)
        s_layout.addWidget(self.spin_line_spacing)

        s_layout.addWidget(QLabel("题间间距:"))
        self.spin_q_spacing = self._make_dspin(1, 15, 5.0, " mm")
        s_layout.addWidget(self.spin_q_spacing)

        s_layout.addWidget(QLabel("选项缩进:"))
        self.spin_opt_indent = self._make_dspin(0, 20, 8.0, " mm")
        s_layout.addWidget(self.spin_opt_indent)

        layout.addWidget(grp_spacing)

        # === 显示选项 ===
        grp_display = QGroupBox("选项")
        d_layout = QVBoxLayout(grp_display)

        self.chk_answer_line = QCheckBox("每题后显示答案横线")
        self.chk_answer_line.setChecked(False)
        self.chk_answer_line.toggled.connect(self._on_config_changed)
        d_layout.addWidget(self.chk_answer_line)

        self.chk_page_num = QCheckBox("显示页码")
        self.chk_page_num.setChecked(True)
        self.chk_page_num.toggled.connect(self._on_config_changed)
        d_layout.addWidget(self.chk_page_num)

        self.chk_keep_last_page = QCheckBox("保留尾页（对答案二维码）")
        self.chk_keep_last_page.setChecked(False)
        self.chk_keep_last_page.setToolTip("勾选后，源PDF最后一页（通常含扫码对答案二维码）将原样保留在输出末尾")
        self.chk_keep_last_page.toggled.connect(self._on_config_changed)
        d_layout.addWidget(self.chk_keep_last_page)
        layout.addWidget(grp_display)

        # === 页边距 ===
        grp_margins = QGroupBox("页边距 (mm)")
        m_layout = QVBoxLayout(grp_margins)
        margins = [("上边距:", "spin_margin_top", 25),
                    ("下边距:", "spin_margin_bottom", 20),
                    ("左边距:", "spin_margin_left", 30),
                    ("右边距:", "spin_margin_right", 25)]

        self._margin_spins = {}
        for label_text, name, default in margins:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            spin = self._make_spin(3, 50, default, " mm")
            row.addWidget(spin)
            m_layout.addLayout(row)
            self._margin_spins[name] = spin
        layout.addWidget(grp_margins)

        # === 按钮 ===
        layout.addSpacing(8)

        btn_apply = QPushButton("▶ 应用并转换")
        btn_apply.setProperty("cssClass", "primary")
        btn_apply.setMinimumHeight(36)
        btn_apply.clicked.connect(lambda: self.convert_now.emit())
        layout.addWidget(btn_apply)

        btn_reset = QPushButton("恢复默认值")
        btn_reset.setProperty("cssClass", "link")
        btn_reset.clicked.connect(self._load_defaults)
        layout.addWidget(btn_reset)

        layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

    # ============================================================
    # 工厂方法
    # ============================================================
    def _make_combo(self, items: list[str]) -> QComboBox:
        c = QComboBox()
        c.addItems(items)
        c.setStyleSheet(COMBOBOX_STYLE)
        # 字体名可能很长（如 "Noto Sans SC Medium"），不能让最长条目撑开
        # 下拉框的最小宽度，否则窄窗口下会把设置列挤出横向滚动条
        c.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        c.setMinimumContentsLength(6)
        c.installEventFilter(_wheel_blocker)
        return c

    def _make_spin(self, lo: int, hi: int, default: int, suffix: str) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(default)
        s.setSuffix(suffix)
        s.setStyleSheet(SPINBOX_STYLE)
        s.installEventFilter(_wheel_blocker)
        s.valueChanged.connect(self._on_config_changed)
        return s

    def _make_dspin(self, lo: float, hi: float, default: float, suffix: str,
                    step: float = 1.0) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setValue(default)
        s.setSingleStep(step)
        s.setSuffix(suffix)
        s.setStyleSheet(SPINBOX_STYLE)
        s.installEventFilter(_wheel_blocker)
        s.valueChanged.connect(self._on_config_changed)
        return s

    # ============================================================
    # 预设
    # ============================================================
    def _apply_preset(self, preset: dict):
        """应用预设参数到UI控件。"""
        self.combo_body_font.setCurrentText(preset.get("body_font", "FangSong"))
        self.spin_body_size.setValue(preset.get("body_size", 14.0))
        self.combo_num_font.setCurrentText(preset.get("num_font", "FangSong"))
        self.combo_opt_font.setCurrentText(preset.get("opt_font", "FangSong"))
        self.spin_opt_size.setValue(preset.get("opt_size", 14.0))
        self.spin_line_spacing.setValue(preset.get("line_spacing", 1.2))
        ps = preset.get("page_size", "B5")
        if ps in PAPER_SIZES:
            self.combo_paper.setCurrentText(ps)
            self._apply_paper_margins(ps)
        self._on_config_changed()

    def _apply_guokao(self):
        """应用国考真题设置: 仿宋 四号(14pt) 行距1.2 B5"""
        self._apply_preset(PRESET_GUOKAO)

    def _apply_liankao(self):
        """应用联考真题设置: 仿宋 小四号(12pt) 行距1.0 B5"""
        self._apply_preset(PRESET_LIANKAO)

    # ============================================================
    # 默认值
    # ============================================================
    def _load_defaults(self):
        self.combo_template.setCurrentIndex(0)
        self.combo_paper.setCurrentText("A4")
        self.combo_body_font.setCurrentText("SimSun")
        self.spin_body_size.setValue(10.5)
        self.combo_num_font.setCurrentText("SimHei")
        self.combo_opt_font.setCurrentText("SimSun")
        self.spin_opt_size.setValue(10.5)
        self.combo_header_font.setCurrentText("SimHei")
        self.spin_header_size.setValue(12.0)
        self.spin_line_spacing.setValue(1.5)
        self.spin_q_spacing.setValue(5.0)
        self.spin_opt_indent.setValue(8.0)
        self.chk_answer_line.setChecked(False)
        self.chk_page_num.setChecked(True)
        self.chk_keep_last_page.setChecked(False)
        for chk in self._drop_checks.values():
            chk.setChecked(False)
        self._set_renumber_choice(False)
        self._apply_paper_margins(self.combo_paper.currentText())
        self._update_drop_enabled()
        self._refresh_drop_ui()

    def get_config(self) -> dict:
        template_map = {0: "xingce", 1: "shenlun"}
        return {
            "template": template_map.get(self.combo_template.currentIndex(), "xingce"),
            "page_size": self.combo_paper.currentText(),
            "header_font": self.combo_header_font.currentText(),
            "header_size": self.spin_header_size.value(),
            "body_font": self.combo_body_font.currentText(),
            "body_size": self.spin_body_size.value(),
            "num_font": self.combo_num_font.currentText(),
            "opt_font": self.combo_opt_font.currentText(),
            "opt_size": self.spin_opt_size.value(),
            "line_spacing": self.spin_line_spacing.value(),
            "question_spacing": self.spin_q_spacing.value(),
            "option_indent": self.spin_opt_indent.value(),
            "show_answer_line": self.chk_answer_line.isChecked(),
            "show_page_number": self.chk_page_num.isChecked(),
            "keep_last_page": self.chk_keep_last_page.isChecked(),
            "drop_sections": [
                key for key, chk in self._drop_checks.items() if chk.isChecked()
            ],
            "renumber_questions": self.radio_renumber.isChecked(),
            "margin_top": self._margin_spins["spin_margin_top"].value(),
            "margin_bottom": self._margin_spins["spin_margin_bottom"].value(),
            "margin_left": self._margin_spins["spin_margin_left"].value(),
            "margin_right": self._margin_spins["spin_margin_right"].value(),
        }

    def apply_config(self, config: dict):
        """把一份已有配置回填到各控件上。

        批量转换对话框用它继承主界面的排版设置 —— 否则用户在"排版设置"里
        选好的字体、纸张、"保留尾页"等参数，在批量转换时会被一份全新的默认值
        默默覆盖掉。
        """
        if not config:
            return

        def _set(spin, value):
            old = spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(old)

        def _select(combo, value):
            if not value:
                return
            old = combo.blockSignals(True)
            combo.setCurrentText(value)
            combo.blockSignals(old)

        template_index = {"xingce": 0, "shenlun": 1}.get(config.get("template"))
        if template_index is not None:
            old = self.combo_template.blockSignals(True)
            self.combo_template.setCurrentIndex(template_index)
            self.combo_template.blockSignals(old)

        paper = config.get("page_size")
        if paper in PAPER_SIZES:
            old = self.combo_paper.blockSignals(True)
            self.combo_paper.setCurrentText(paper)
            self.combo_paper.blockSignals(old)
            # 先铺该纸张的默认边距，再由配置里的显式边距覆盖（顺序不能反）
            self._apply_paper_margins(paper)

        for combo, key in ((self.combo_body_font, "body_font"),
                           (self.combo_num_font, "num_font"),
                           (self.combo_opt_font, "opt_font"),
                           (self.combo_header_font, "header_font")):
            _select(combo, config.get(key))

        for spin, key in ((self.spin_body_size, "body_size"),
                          (self.spin_opt_size, "opt_size"),
                          (self.spin_header_size, "header_size"),
                          (self.spin_line_spacing, "line_spacing"),
                          (self.spin_q_spacing, "question_spacing"),
                          (self.spin_opt_indent, "option_indent")):
            if config.get(key) is not None:
                _set(spin, float(config[key]))

        for name, key in (("spin_margin_top", "margin_top"),
                          ("spin_margin_bottom", "margin_bottom"),
                          ("spin_margin_left", "margin_left"),
                          ("spin_margin_right", "margin_right")):
            spin = self._margin_spins.get(name)
            if spin is not None and config.get(key) is not None:
                _set(spin, int(round(float(config[key]))))  # 页边距是整数 QSpinBox

        for chk, key, default in ((self.chk_answer_line, "show_answer_line", False),
                                  (self.chk_page_num, "show_page_number", True),
                                  (self.chk_keep_last_page, "keep_last_page", False)):
            old = chk.blockSignals(True)
            chk.setChecked(bool(config.get(key, default)))
            chk.blockSignals(old)

        drop_values = config.get("drop_sections")
        if drop_values is not None:
            selected = {str(name) for name in drop_values}
            for key, chk in self._drop_checks.items():
                old = chk.blockSignals(True)
                chk.setChecked(key in selected)
                chk.blockSignals(old)

        renumber = config.get("renumber_questions")
        if renumber is not None:
            self._set_renumber_choice(bool(renumber))

        self._on_config_changed()

    def _on_config_changed(self, *args):
        self._update_drop_enabled()
        self._refresh_drop_ui()
        self.config_changed.emit(self.get_config())

    def _set_renumber_choice(self, renumber: bool):
        """静默设置题号处理方式。

        两个 QRadioButton 自动互斥，切换时会互相触发 toggled，必须同时
        屏蔽两者的信号，避免回填配置时产生多次 config_changed。
        """
        old_renumber = self.radio_renumber.blockSignals(True)
        old_keep = self.radio_keep_numbers.blockSignals(True)
        self.radio_renumber.setChecked(renumber)
        self.radio_keep_numbers.setChecked(not renumber)
        self.radio_keep_numbers.blockSignals(old_keep)
        self.radio_renumber.blockSignals(old_renumber)

    def _refresh_drop_ui(self):
        """刷新"已选 N 个模块"提示与清空按钮的可见性。"""
        selected = [key for key, chk in self._drop_checks.items() if chk.isChecked()]
        self._drop_footer.setVisible(bool(selected))
        if selected:
            self._drop_summary.setText(f"将删除 {len(selected)} 个模块")

    def _clear_drop_sections(self):
        """一键取消全部模块删除勾选。"""
        selected = [chk for chk in self._drop_checks.values() if chk.isChecked()]
        if not selected:
            return
        for chk in selected:
            old = chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(old)
        self._on_config_changed()

    def _update_drop_enabled(self):
        """模块删除只对行测有效: 选申论时整组隐藏并清空勾选。

        隐藏而不只是置灰 —— 申论没有"模块"概念，留着控件容易被误勾选。
        同时清空勾选: 免得从行测切到申论再切回来时，勾着的"删除"还在，
        下一次转换莫名其妙少了一整个模块。
        """
        grp = getattr(self, "_grp_drop", None)
        if grp is None:
            return
        is_xingce = self.combo_template.currentIndex() == 0
        if not is_xingce:
            for chk in self._drop_checks.values():
                old = chk.blockSignals(True)
                chk.setChecked(False)
                chk.blockSignals(old)
        grp.setVisible(is_xingce)

    def _on_paper_changed(self, paper: str):
        self._apply_paper_margins(paper)
        self._on_config_changed()

    def _apply_paper_margins(self, paper: str):
        if not hasattr(self, "_margin_spins"):
            return
        margins = PAPER_MARGIN_PRESETS.get(paper)
        if not margins:
            return
        mapping = {
            "spin_margin_top": margins["top"],
            "spin_margin_bottom": margins["bottom"],
            "spin_margin_left": margins["left"],
            "spin_margin_right": margins["right"],
        }
        for name, value in mapping.items():
            spin = self._margin_spins[name]
            old = spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(old)

    def update_fonts(self, fonts: list[str]):
        self._fonts = fonts
        for combo in [self.combo_header_font, self.combo_body_font,
                       self.combo_num_font, self.combo_opt_font]:
            current = combo.currentText()
            combo.clear()
            combo.addItems(fonts)
            if current in fonts:
                combo.setCurrentText(current)
