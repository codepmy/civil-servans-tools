"""考试计时器 — 大字自适应显示 + 正/倒计时 + 右侧分段列表。"""

from PyQt6.QtCore import Qt, QTimer as QtFlashTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QButtonGroup,
    QSpinBox, QScrollArea, QFrame,
)
from PyQt6.QtGui import QFont

from tools.exam_timer.core.timer_engine import TimerEngine


class TimerWidget(QWidget):
    """计时器主页面。"""

    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._engine = TimerEngine()
        self._flash_timer = QtFlashTimer()
        self._flash_timer.setInterval(400)
        self._flash_timer.timeout.connect(self._toggle_flash)
        self._flash_on = False
        self._is_countdown_done = False
        self._base_font_size = 180

        self._setup_ui()
        self._connect_signals()

        self.btn_countup.setChecked(True)
        self._apply_mode("countup")

    # ═══════════════════════════════════════
    #  自适应字号
    # ═══════════════════════════════════════

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_font_size()

    def _update_font_size(self):
        """根据可用高度动态计算时间字号。"""
        avail = max(260, self.height() - 180)
        size = max(140, min(int(avail * 0.68), 430))
        if abs(size - self._base_font_size) > 2:
            self._base_font_size = size
            self.label_time.setFont(QFont("Consolas, Microsoft YaHei", size, QFont.Weight.Bold))

    # ═══════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_left_panel(), stretch=7)
        root.addWidget(self._build_right_panel(), stretch=3)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: #F8F7F4;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(48, 28, 48, 28)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.btn_back = QPushButton("< 返回首页")
        self.btn_back.setFixedSize(104, 34)
        self.btn_back.setStyleSheet(
            "QPushButton { background-color: #F3F4F6; border: 1px solid #E5E7EB; "
            "border-radius: 17px; font-weight: 600; color: #374151; }"
            "QPushButton:hover { background-color: #E5E7EB; border-color: #D1D5DB; }"
        )
        header.addWidget(self.btn_back)
        header.addStretch()
        layout.addLayout(header)

        # 模式切换
        layout.addLayout(self._build_mode_switch())

        # ═══ 倒计时设置 ═══
        self.frame_target = QFrame()
        self.frame_target.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px; }"
        )
        target_outer = QHBoxLayout(self.frame_target)
        target_outer.setContentsMargins(16, 10, 16, 10)
        target_outer.addStretch()

        target_inner = QHBoxLayout()
        target_inner.setSpacing(6)
        lbl = QLabel("⏲ 倒计时至")
        lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #374151; border: none;")
        target_inner.addWidget(lbl)
        target_inner.addSpacing(8)
        self._build_time_inputs(target_inner)
        target_outer.addLayout(target_inner)

        target_outer.addStretch()
        self.frame_target.hide()
        layout.addWidget(self.frame_target)

        layout.addStretch(1)

        # ═══ 大号时间 ═══
        self.label_time = QLabel("00 : 00 : 00")
        self.label_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_time.setFont(QFont("Consolas, Microsoft YaHei", 180, QFont.Weight.Bold))
        self.label_time.setStyleSheet("color: #1F2937;")
        # 让 label 尽可能扩展以填充空间
        self.label_time.setSizePolicy(
            self.label_time.sizePolicy().horizontalPolicy(),
            self.label_time.sizePolicy().verticalPolicy(),
        )
        layout.addWidget(self.label_time, stretch=10)

        self.label_sub = QLabel("已用时间")
        self.label_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_sub.setStyleSheet("font-size: 14px; color: #9CA3AF; padding-bottom: 4px;")
        layout.addWidget(self.label_sub)

        layout.addStretch(1)

        # 控制按钮
        layout.addLayout(self._build_controls())

        return panel

    def _build_mode_switch(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        layout.addStretch()

        self._mode_group = QButtonGroup(self)

        self.btn_countup = QRadioButton("正计时")
        self.btn_countdown = QRadioButton("倒计时")
        self._mode_group.addButton(self.btn_countup, 0)
        self._mode_group.addButton(self.btn_countdown, 1)

        for btn in (self.btn_countup, self.btn_countdown):
            btn.setStyleSheet(
                "QRadioButton { padding: 6px 18px; border: 1px solid #D1D5DB; "
                "border-radius: 6px; background: #FFFFFF; font-size: 14px; color: #374151; }"
                "QRadioButton:hover { border-color: #4F46E5; background: #F5F3FF; }"
                "QRadioButton:checked { background: #EEF2FF; border-color: #4F46E5; "
                "color: #4338CA; font-weight: 600; }"
            )
            layout.addWidget(btn)

        layout.addStretch()
        return layout

    def _build_time_inputs(self, parent_layout):
        """HH : MM : SS 三个输入框。"""
        spin_style = (
            "QSpinBox { font-size: 17px; font-weight: 600; padding: 6px 2px; "
            "border: 1px solid #D1D5DB; border-radius: 6px; background: #FFFFFF; "
            "min-width: 58px; text-align: center; }"
            "QSpinBox:focus { border-color: #4F46E5; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 18px; }"
        )

        self.spin_h = QSpinBox()
        self.spin_h.setRange(0, 99)
        self.spin_h.setValue(2)
        self.spin_h.setSuffix(" 时")
        self.spin_h.setStyleSheet(spin_style)
        parent_layout.addWidget(self.spin_h)

        sep1 = QLabel(":")
        sep1.setStyleSheet("font-size: 20px; font-weight: 700; color: #374151; border: none; margin: 0 2px;")
        parent_layout.addWidget(sep1)

        self.spin_m = QSpinBox()
        self.spin_m.setRange(0, 59)
        self.spin_m.setValue(0)
        self.spin_m.setSuffix(" 分")
        self.spin_m.setStyleSheet(spin_style)
        parent_layout.addWidget(self.spin_m)

        sep2 = QLabel(":")
        sep2.setStyleSheet("font-size: 20px; font-weight: 700; color: #374151; border: none; margin: 0 2px;")
        parent_layout.addWidget(sep2)

        self.spin_s = QSpinBox()
        self.spin_s.setRange(0, 59)
        self.spin_s.setValue(0)
        self.spin_s.setSuffix(" 秒")
        self.spin_s.setStyleSheet(spin_style)
        parent_layout.addWidget(self.spin_s)

    def _build_controls(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)
        layout.addStretch()

        self.btn_start = self._make_btn("▶ 开始", "#4F46E5", "#FFFFFF",
                                         hover_bg="#4338CA", press_bg="#3730A3")
        layout.addWidget(self.btn_start)

        self.btn_pause = self._make_btn("⏸ 暂停", "#F3F4F6", "#374151")
        self.btn_pause.setEnabled(False)
        layout.addWidget(self.btn_pause)

        self.btn_lap = self._make_btn("🏁 分段", "#F3F4F6", "#374151")
        self.btn_lap.setEnabled(False)
        layout.addWidget(self.btn_lap)

        self.btn_reset = self._make_btn("↺ 重置", "#F3F4F6", "#374151")
        layout.addWidget(self.btn_reset)

        layout.addStretch()
        return layout

    def _make_btn(self, text: str, bg: str, fg: str,
                  hover_bg: str = "#E5E7EB", press_bg: str = "#D1D5DB") -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumHeight(44)
        btn.setMinimumWidth(100)
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {bg}; color: {fg}; border: "
            f"{'none' if bg != '#F3F4F6' else '1px solid #E5E7EB'}; "
            f"border-radius: 8px; font-size: 15px; font-weight: 600; padding: 8px 20px; }}"
            f"QPushButton:hover {{ background-color: {hover_bg}; }}"
            f"QPushButton:pressed {{ background-color: {press_bg}; }}"
            f"QPushButton:disabled {{ background-color: #F3F4F6; color: #9CA3AF; border: 1px solid #E5E7EB; }}"
        )
        return btn

    # ── 右侧：分段记录 ──

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: #FFFFFF; border-left: 1px solid #E5E7EB;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("📋 分段记录")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #111827; border: none;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.lap_container = QWidget()
        self.lap_container.setStyleSheet("background: transparent;")
        self.lap_layout = QVBoxLayout(self.lap_container)
        self.lap_layout.setContentsMargins(0, 0, 0, 0)
        self.lap_layout.setSpacing(4)
        self.lap_layout.addStretch()
        scroll.setWidget(self.lap_container)

        layout.addWidget(scroll, stretch=1)

        self.lap_empty = QLabel("暂无记录\n点击「🏁 分段」记录")
        self.lap_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lap_empty.setStyleSheet("color: #D1D5DB; font-size: 13px; border: none; padding: 24px;")
        self.lap_layout.insertWidget(0, self.lap_empty)

        return panel

    # ═══════════════════════════════════════
    #  信号连接
    # ═══════════════════════════════════════

    def _connect_signals(self):
        self._engine.tick.connect(self._on_tick)
        self._engine.time_up.connect(self._on_time_up)
        self._engine.lap_recorded.connect(self._on_lap_recorded)
        self._engine.state_changed.connect(self._on_state_changed)

        # 使用 buttonGroup 的 idToggled 避免 radio 信号时序问题
        self._mode_group.idToggled.connect(self._on_mode_toggled)

        self.btn_start.clicked.connect(lambda: self._engine.start())
        self.btn_pause.clicked.connect(lambda: self._engine.pause())
        self.btn_lap.clicked.connect(lambda: self._engine.record_lap())
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_back.clicked.connect(self.back_requested.emit)

        for spin in (self.spin_h, self.spin_m, self.spin_s):
            spin.valueChanged.connect(self._on_countdown_target_changed)

    # ═══════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════

    def _on_mode_toggled(self, btn_id: int, checked: bool):
        """QButtonGroup 模式切换 — 只在选中时触发。"""
        if not checked:
            return
        mode = "countup" if btn_id == 0 else "countdown"
        self._apply_mode(mode)

    def _apply_mode(self, mode: str):
        self._engine.reset()
        self._engine.set_mode(mode)
        self.frame_target.setVisible(mode == "countdown")
        self.label_sub.setText("剩余时间" if mode == "countdown" else "已用时间")
        if mode == "countdown":
            self._on_countdown_target_changed()

    def _on_countdown_target_changed(self):
        if self._engine.state.mode != "countdown":
            return
        total = self.spin_h.value() * 3600 + self.spin_m.value() * 60 + self.spin_s.value()
        if total > 0:
            self._engine.set_countdown_target(total)

    def _on_reset(self):
        self._engine.reset()
        self._clear_lap_list()
        self._stop_flash()
        self._is_countdown_done = False

    def _on_tick(self, elapsed: int, total: int, mode: str):
        if mode == "countdown":
            remaining = max(0, total - elapsed)
            display = remaining
        else:
            display = elapsed

        self.label_time.setText(self._fmt(display))

        if mode == "countdown" and 0 < (total - elapsed) <= 300:
            self._set_time_color("#EF4444")
        else:
            self._set_time_color("#1F2937")

    def _on_state_changed(self, state):
        if state.is_running:
            self.btn_start.setText("▶ 继续")
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_lap.setEnabled(True)
            self._set_mode_enabled(False)
            self._stop_flash()
        elif state.elapsed_seconds > 0 and not state.is_running and not self._is_countdown_done:
            self.btn_start.setText("▶ 继续")
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_lap.setEnabled(False)
        else:
            self.btn_start.setText("▶ 开始")
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_lap.setEnabled(False)
            self._set_mode_enabled(True)

    def _set_mode_enabled(self, enabled: bool):
        self.btn_countup.setEnabled(enabled)
        self.btn_countdown.setEnabled(enabled)
        self.spin_h.setEnabled(enabled)
        self.spin_m.setEnabled(enabled)
        self.spin_s.setEnabled(enabled)

    def _on_time_up(self):
        self._set_time_color("#EF4444")
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_lap.setEnabled(False)
        self._is_countdown_done = True
        self._flash_on = True
        self._flash_timer.start()
        self.label_sub.setText("⏰ 时间到！")

    def _on_lap_recorded(self, entry):
        self.lap_empty.hide()
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; }"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 6, 10, 6)

        idx = QLabel(f"#{entry.index}")
        idx.setStyleSheet("font-weight: 600; color: #4F46E5; border: none; font-size: 13px;")
        rl.addWidget(idx)
        rl.addStretch()

        tm = QLabel(self._fmt(entry.elapsed))
        tm.setStyleSheet("color: #374151; font-weight: 500; border: none; font-size: 13px;")
        rl.addWidget(tm)

        # 插入到 stretch 之前
        self.lap_layout.insertWidget(self.lap_layout.count() - 1, row)

    # ═══════════════════════════════════════
    #  辅助
    # ═══════════════════════════════════════

    def _set_time_color(self, color: str):
        self.label_time.setStyleSheet(f"color: {color};")

    def _toggle_flash(self):
        self._flash_on = not self._flash_on
        self._set_time_color("#EF4444" if self._flash_on else "#FCA5A5")

    def _stop_flash(self):
        self._flash_timer.stop()
        self._flash_on = False
        self._set_time_color("#1F2937")
        self.label_sub.setText(self.label_sub.text().replace("⏰ 时间到！", "剩余时间"))

    def _clear_lap_list(self):
        """清空分段记录，保留空状态提示。"""
        for i in reversed(range(self.lap_layout.count())):
            item = self.lap_layout.itemAt(i)
            w = item.widget() if item else None
            if w and w is not self.lap_empty:
                w.deleteLater()
                self.lap_layout.removeItem(item)
        self.lap_empty.show()

    @staticmethod
    def _fmt(seconds: int) -> str:
        s = max(0, seconds)
        h, m = divmod(s, 3600)
        m, s = divmod(m, 60)
        return f"{h:02d} : {m:02d} : {s:02d}"
