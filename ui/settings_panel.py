"""右侧设置面板: 调整排版参数(字体/字号/行距/边距等)。"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDoubleSpinBox, QCheckBox, QPushButton, QGroupBox,
    QScrollArea, QRadioButton, QSpinBox,
)
from PyQt6.QtCore import pyqtSignal, QEvent, QObject


# ============================================================
# 滚轮事件过滤器: 阻止鼠标滚轮修改 QSpinBox/QComboBox 的值
# ============================================================
class _WheelBlockFilter(QObject):
    """拦截滚轮事件。"""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            return True
        return super().eventFilter(obj, event)

_wheel_blocker = _WheelBlockFilter()

# 控件基础样式
SPINBOX_STYLE = "QSpinBox, QDoubleSpinBox { padding: 4px 8px; font-size: 13px; min-height: 28px; }"
COMBOBOX_STYLE = "QComboBox { padding: 4px 8px; font-size: 13px; min-height: 28px; }"

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
        title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
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

        # === 快速预设 ===
        grp_preset = QGroupBox("快速预设")
        p_layout = QVBoxLayout(grp_preset)
        self.btn_guokao = QPushButton("🏛 国考真题字体设置")
        self.btn_guokao.setToolTip("仿宋 四号(14pt) 行距1.2 B5纸")
        self.btn_guokao.clicked.connect(self._apply_guokao)
        self.btn_guokao.setStyleSheet(
            "QPushButton { background-color: #FFF3E0; border: 1px solid #FF9800; "
            "border-radius: 4px; padding: 6px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background-color: #FFE0B2; }"
        )
        p_layout.addWidget(self.btn_guokao)

        self.btn_liankao = QPushButton("📝 联考真题字体设置")
        self.btn_liankao.setToolTip("仿宋 小四号(12pt) 行距1.0 B5纸")
        self.btn_liankao.clicked.connect(self._apply_liankao)
        self.btn_liankao.setStyleSheet(
            "QPushButton { background-color: #E8F5E9; border: 1px solid #4CAF50; "
            "border-radius: 4px; padding: 6px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background-color: #C8E6C9; }"
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
        btn_apply.setStyleSheet(
            "QPushButton { background-color: #0078D4; color: white; font-weight: bold; "
            "padding: 8px; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #106EBE; }"
        )
        btn_apply.clicked.connect(lambda: self.convert_now.emit())
        layout.addWidget(btn_apply)

        btn_reset = QPushButton("恢复默认值")
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
        self._apply_paper_margins(self.combo_paper.currentText())

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
            "margin_top": self._margin_spins["spin_margin_top"].value(),
            "margin_bottom": self._margin_spins["spin_margin_bottom"].value(),
            "margin_left": self._margin_spins["spin_margin_left"].value(),
            "margin_right": self._margin_spins["spin_margin_right"].value(),
        }

    def _on_config_changed(self, *args):
        self.config_changed.emit(self.get_config())

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
