"""计时引擎（简洁版）：正计时 / 倒计时 + 分段记录。"""

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from tools.exam_timer.core.models import TimerState, LapEntry


class TimerEngine(QObject):
    """计时引擎。

    Signals:
        tick: 每秒触发 (elapsed_seconds, total_seconds, mode)
        time_up: 倒计时归零时触发
        lap_recorded: 新分段记录 (LapEntry)
        state_changed: 状态变化 (TimerState)
    """

    tick = pyqtSignal(int, int, str)      # elapsed, total, mode
    time_up = pyqtSignal()
    lap_recorded = pyqtSignal(LapEntry)
    state_changed = pyqtSignal(TimerState)

    def __init__(self):
        super().__init__()
        self._state = TimerState()
        self._qt_timer = QTimer()
        self._qt_timer.setInterval(100)
        self._qt_timer.timeout.connect(self._on_timeout)
        self._tick_count = 0

    # ── API ──

    def set_mode(self, mode: str):
        """切换正计时/倒计时。"""
        self._state.mode = mode
        self._state.elapsed_seconds = 0
        self._state.total_seconds = 0
        self.state_changed.emit(self._state)
        self.tick.emit(0, 0, mode)

    def set_countdown_target(self, total_seconds: int):
        """设置倒计时目标秒数。"""
        self._state.mode = "countdown"
        self._state.total_seconds = max(1, total_seconds)
        self._state.elapsed_seconds = 0
        self.state_changed.emit(self._state)
        self.tick.emit(0, self._state.total_seconds, "countdown")

    def start(self):
        if not self._state.is_running:
            self._state.is_running = True
            self._qt_timer.start()
            self.state_changed.emit(self._state)

    def pause(self):
        if self._state.is_running:
            self._state.is_running = False
            self._qt_timer.stop()
            self.state_changed.emit(self._state)

    def reset(self):
        self._qt_timer.stop()
        self._state.is_running = False
        self._state.elapsed_seconds = 0
        self._state.laps.clear()
        self.state_changed.emit(self._state)
        self.tick.emit(0, self._state.total_seconds, self._state.mode)

    def record_lap(self):
        """记录当前时间为一个分段。"""
        entry = LapEntry(
            index=len(self._state.laps) + 1,
            elapsed=self._state.elapsed_seconds,
        )
        self._state.laps.append(entry)
        self.lap_recorded.emit(entry)

    # ── internal ──

    def _on_timeout(self):
        self._tick_count += 1
        if self._tick_count >= 10:           # 100ms × 10 = 1s
            self._tick_count = 0
            self._state.elapsed_seconds += 1
            self.tick.emit(
                self._state.elapsed_seconds,
                self._state.total_seconds,
                self._state.mode,
            )

            if self._state.mode == "countdown" and self._state.total_seconds > 0:
                remaining = self._state.total_seconds - self._state.elapsed_seconds
                if remaining <= 0:
                    self._state.is_running = False
                    self._qt_timer.stop()
                    self.time_up.emit()

    @property
    def state(self) -> TimerState:
        return self._state
