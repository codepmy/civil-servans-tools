"""Exam timer page with an adaptive, large time display."""

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tools.exam_timer.core.timer_engine import TimerEngine


class TimerWidget(QWidget):
    """Main exam timer page."""

    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._engines = {
            "countup": TimerEngine(),
            "countdown": TimerEngine(),
        }
        self._engine = self._engines["countup"]
        self._active_mode = "countup"
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(400)
        self._flash_timer.timeout.connect(self._toggle_flash)
        self._flash_on = False
        self._is_countdown_done = False
        self._time_color = "#1F2937"
        self._time_font_size = 260
        self._min_time_font_size = 48
        self._max_time_font_size = 760
        self._time_font_family = "Consolas"
        self._font_update_pending = False

        self._setup_ui()
        self._engines["countdown"].set_mode("countdown")
        self._engines["countdown"].set_countdown_target(self._countdown_total_seconds())
        self._connect_signals()

        self.btn_countup.setChecked(True)
        self._apply_mode("countup")
        self._schedule_font_update()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_font_update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_font_update()

    def eventFilter(self, obj, event):
        if obj in (getattr(self, "label_time", None), getattr(self, "left_panel", None)):
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
                self._schedule_font_update()
        return super().eventFilter(obj, event)

    def _schedule_font_update(self):
        if self._font_update_pending:
            return
        self._font_update_pending = True
        QTimer.singleShot(0, self._update_font_size)

    def _update_font_size(self):
        self._font_update_pending = False
        if not hasattr(self, "label_time") or self.label_time.width() <= 0:
            return

        rect = self.label_time.contentsRect()
        avail_w = max(1, rect.width() - 16)
        avail_h = max(1, rect.height() - 16)
        text = self.label_time.text() or "00 : 00 : 00"

        low = self._min_time_font_size
        high = self._max_time_font_size
        best = low
        while low <= high:
            mid = (low + high) // 2
            metrics = QFontMetrics(self._time_font(mid))
            bounds = metrics.boundingRect(text)
            if bounds.width() <= avail_w and metrics.height() <= avail_h:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        if abs(best - self._time_font_size) > 1:
            self._time_font_size = best
            self._apply_time_style()

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(14)
        root.addWidget(self._build_left_panel(), stretch=5)
        root.addWidget(self._build_right_panel(), stretch=3)

    def _build_left_panel(self) -> QWidget:
        self.left_panel = QWidget()
        self.left_panel.setObjectName("tool-page")
        self.left_panel.installEventFilter(self)

        layout = QVBoxLayout(self.left_panel)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        # 顶栏：返回按钮 + 标题
        header = QHBoxLayout()
        header.setSpacing(12)
        self.btn_back = QPushButton("←")
        self.btn_back.setObjectName("btn-back")
        self.btn_back.setToolTip("返回首页")
        header.addWidget(self.btn_back)

        title = QLabel("考试计时器")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #111827;"
            "background: transparent; border: none;"
        )
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        layout.addLayout(self._build_mode_switch())

        self.frame_target = QFrame()
        self.frame_target.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px; }"
        )
        target_outer = QHBoxLayout(self.frame_target)
        target_outer.setContentsMargins(16, 10, 16, 10)
        target_outer.addStretch()

        target_inner = QHBoxLayout()
        target_inner.setSpacing(6)
        lbl = QLabel("倒计时至")
        lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #374151; border: none;")
        target_inner.addWidget(lbl)
        target_inner.addSpacing(8)
        self._build_time_inputs(target_inner)
        target_outer.addLayout(target_inner)
        target_outer.addStretch()

        self.frame_target.hide()
        layout.addWidget(self.frame_target)

        layout.addStretch(1)

        self.label_time = QLabel("00 : 00 : 00")
        self.label_time.setObjectName("timer-time")
        self.label_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_time.setMinimumHeight(120)
        self.label_time.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.label_time.installEventFilter(self)
        self._apply_time_style()
        layout.addWidget(self.label_time, stretch=12)

        self.label_sub = QLabel("已用时间")
        self.label_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_sub.setStyleSheet("font-size: 14px; color: #9CA3AF; padding-bottom: 4px;")
        layout.addWidget(self.label_sub)

        layout.addStretch(1)
        layout.addLayout(self._build_controls())

        return self.left_panel

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
                "QRadioButton { padding: 7px 20px; border: 1px solid #D1D5DB; "
                "border-radius: 8px; background: #FFFFFF; font-size: 13px; "
                "font-weight: 500; color: #374151; }"
                "QRadioButton:hover { border-color: #4F46E5; background: #F5F3FF; }"
                "QRadioButton:checked { background: #EEF2FF; border-color: #4F46E5; "
                "color: #4338CA; font-weight: 700; }"
            )
            layout.addWidget(btn)

        layout.addStretch()
        return layout

    def _build_time_inputs(self, parent_layout):
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

        self.btn_start = self._make_btn("开始", "#4F46E5", "#FFFFFF", hover_bg="#4338CA", press_bg="#3730A3")
        self.btn_pause = self._make_btn("暂停", "#F3F4F6", "#374151")
        self.btn_lap = self._make_btn("分段", "#F3F4F6", "#374151")
        self.btn_reset = self._make_btn("重置", "#F3F4F6", "#374151")
        self.btn_pause.setEnabled(False)
        self.btn_lap.setEnabled(False)

        for btn in (self.btn_start, self.btn_pause, self.btn_lap, self.btn_reset):
            layout.addWidget(btn)

        layout.addStretch()
        return layout

    def _make_btn(
        self,
        text: str,
        bg: str,
        fg: str,
        hover_bg: str = "#E5E7EB",
        press_bg: str = "#D1D5DB",
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumHeight(44)
        btn.setMinimumWidth(100)
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {bg}; color: {fg}; border: "
            f"{'none' if bg != '#F3F4F6' else '1px solid #E5E7EB'}; "
            f"border-radius: 8px; font-size: 15px; font-weight: 600; padding: 8px 20px; }}"
            f"QPushButton:hover {{ background-color: {hover_bg}; }}"
            f"QPushButton:pressed {{ background-color: {press_bg}; }}"
            "QPushButton:disabled { background-color: #F3F4F6; color: #9CA3AF; border: 1px solid #E5E7EB; }"
        )
        return btn

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(300)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        panel.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px;"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("分段记录")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #111827; border: none; background: transparent;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(280)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.lap_container = QWidget()
        self.lap_container.setStyleSheet("background: transparent;")
        self.lap_layout = QVBoxLayout(self.lap_container)
        self.lap_layout.setContentsMargins(0, 0, 0, 0)
        self.lap_layout.setSpacing(4)
        self.lap_layout.addStretch()
        scroll.setWidget(self.lap_container)

        layout.addWidget(scroll, stretch=1)

        self.lap_empty = QLabel("暂无记录\n点击“分段”记录")
        self.lap_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lap_empty.setWordWrap(True)
        self.lap_empty.setStyleSheet("color: #D1D5DB; font-size: 13px; border: none; padding: 24px;")
        self.lap_layout.insertWidget(0, self.lap_empty)

        return panel

    def _connect_signals(self):
        for engine in self._engines.values():
            engine.tick.connect(self._on_tick)
            engine.time_up.connect(self._on_time_up)
            engine.lap_recorded.connect(self._on_lap_recorded)
            engine.state_changed.connect(self._on_state_changed)
        self._mode_group.idToggled.connect(self._on_mode_toggled)

        self.btn_start.clicked.connect(lambda: self._current_engine().start())
        self.btn_pause.clicked.connect(lambda: self._current_engine().pause())
        self.btn_lap.clicked.connect(lambda: self._current_engine().record_lap())
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_back.clicked.connect(self.back_requested.emit)

        for spin in (self.spin_h, self.spin_m, self.spin_s):
            spin.valueChanged.connect(self._on_countdown_target_changed)

    def _current_engine(self) -> TimerEngine:
        return self._engines[self._active_mode]

    def _countdown_total_seconds(self) -> int:
        return max(1, self.spin_h.value() * 3600 + self.spin_m.value() * 60 + self.spin_s.value())

    def _refresh_active_view(self, rebuild_laps: bool = False):
        engine = self._current_engine()
        state = engine.state
        if state.mode == "countdown":
            display = max(0, state.total_seconds - state.elapsed_seconds)
            done = state.total_seconds > 0 and state.elapsed_seconds >= state.total_seconds
            self.label_sub.setText("时间到！" if done else "剩余时间")
            self._set_time_color("#EF4444" if done else "#1F2937")
        else:
            display = state.elapsed_seconds
            self.label_sub.setText("已用时间")
            self._set_time_color("#1F2937")

        self.label_time.setText(self._fmt(display))
        self._refresh_controls_from_state(state)
        if rebuild_laps:
            self._rebuild_lap_list(state.laps)
        self._schedule_font_update()

    def _refresh_controls_from_state(self, state):
        countdown_done = (
            state.mode == "countdown"
            and state.total_seconds > 0
            and state.elapsed_seconds >= state.total_seconds
        )
        if state.is_running:
            self.btn_start.setText("继续")
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_lap.setEnabled(True)
            self._set_mode_enabled(False)
        elif countdown_done:
            self.btn_start.setText("开始")
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_lap.setEnabled(False)
            self._set_mode_enabled(True)
        elif state.elapsed_seconds > 0:
            self.btn_start.setText("继续")
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_lap.setEnabled(False)
            self._set_mode_enabled(state.mode != "countdown")
        else:
            self.btn_start.setText("开始")
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_lap.setEnabled(False)
            self._set_mode_enabled(True)

    def _on_mode_toggled(self, btn_id: int, checked: bool):
        if not checked:
            return
        self._apply_mode("countup" if btn_id == 0 else "countdown")

    def _apply_mode(self, mode: str):
        self._active_mode = mode
        self._engine = self._engines[mode]
        self.frame_target.setVisible(mode == "countdown")
        if mode == "countdown" and self._engine.state.total_seconds <= 0:
            self._engine.set_countdown_target(self._countdown_total_seconds())
        self._refresh_active_view(rebuild_laps=True)
        self._schedule_font_update()

    def _on_countdown_target_changed(self):
        engine = self._engines["countdown"]
        if engine.state.is_running:
            return
        total = self._countdown_total_seconds()
        if total > 0:
            engine.set_countdown_target(total)
            self._is_countdown_done = False
            if self._active_mode == "countdown":
                self._refresh_active_view(rebuild_laps=False)

    def _on_reset(self):
        self._current_engine().reset()
        self._clear_lap_list()
        self._stop_flash()
        if self._active_mode == "countdown":
            self._is_countdown_done = False
        self._refresh_active_view(rebuild_laps=True)

    def _on_tick(self, elapsed: int, total: int, mode: str):
        if self.sender() is not self._current_engine():
            return
        if mode == "countdown":
            remaining = max(0, total - elapsed)
            display = remaining
        else:
            display = elapsed

        self.label_time.setText(self._fmt(display))
        self._schedule_font_update()

        if mode == "countdown" and 0 < (total - elapsed) <= 300:
            self._set_time_color("#EF4444")
        else:
            self._set_time_color("#1F2937")

    def _on_state_changed(self, state):
        if self.sender() is not self._current_engine():
            return
        if state.is_running:
            self._stop_flash()
        self._refresh_active_view(rebuild_laps=False)

    def _set_mode_enabled(self, enabled: bool):
        self.btn_countup.setEnabled(True)
        self.btn_countdown.setEnabled(True)
        self.spin_h.setEnabled(enabled)
        self.spin_m.setEnabled(enabled)
        self.spin_s.setEnabled(enabled)

    def _on_time_up(self):
        if self.sender() is not self._engines["countdown"]:
            return
        self._is_countdown_done = True
        if self._active_mode != "countdown":
            return
        self._refresh_active_view(rebuild_laps=False)
        self._flash_on = True
        self._flash_timer.start()
        self.label_sub.setText("时间到！")

    def _on_lap_recorded(self, entry):
        if self.sender() is not self._current_engine():
            return
        self._add_lap_row(entry)

    def _add_lap_row(self, entry):
        self.lap_empty.hide()
        row = QFrame()
        row.setStyleSheet("QFrame { background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; }")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 6, 10, 6)

        idx = QLabel(f"#{entry.index}")
        idx.setStyleSheet("font-weight: 600; color: #4F46E5; border: none; font-size: 13px;")
        idx.setMinimumWidth(36)
        row_layout.addWidget(idx)
        row_layout.addStretch()

        tm = QLabel(self._fmt(entry.elapsed))
        tm.setStyleSheet("color: #374151; font-weight: 500; border: none; font-size: 13px;")
        tm.setMinimumWidth(96)
        tm.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(tm)

        self.lap_layout.insertWidget(self.lap_layout.count() - 1, row)

    def _set_time_color(self, color: str):
        if self._time_color == color:
            return
        self._time_color = color
        self._apply_time_style()

    def _time_font(self, size: int) -> QFont:
        font = QFont(self._time_font_family)
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.Bold)
        return font

    def _apply_time_style(self):
        self.label_time.setFont(self._time_font(self._time_font_size))
        self.label_time.setStyleSheet(
            "QLabel#timer-time { "
            "border: none; background: transparent; "
            f"color: {self._time_color}; "
            f"font-family: {self._time_font_family}, 'Microsoft YaHei'; "
            f"font-size: {self._time_font_size}px; "
            "font-weight: 900; "
            "}"
        )

    def _toggle_flash(self):
        self._flash_on = not self._flash_on
        self._set_time_color("#EF4444" if self._flash_on else "#FCA5A5")

    def _stop_flash(self):
        self._flash_timer.stop()
        self._flash_on = False
        self._set_time_color("#1F2937")
        if self._active_mode == "countdown":
            self.label_sub.setText("剩余时间")

    def _clear_lap_list(self):
        for i in reversed(range(self.lap_layout.count())):
            item = self.lap_layout.itemAt(i)
            widget = item.widget() if item else None
            if widget and widget is not self.lap_empty:
                widget.deleteLater()
                self.lap_layout.removeItem(item)
        self.lap_empty.show()

    def _rebuild_lap_list(self, laps):
        self._clear_lap_list()
        for entry in laps:
            self._add_lap_row(entry)

    @staticmethod
    def _fmt(seconds: int) -> str:
        seconds = max(0, seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d} : {minutes:02d} : {seconds:02d}"
