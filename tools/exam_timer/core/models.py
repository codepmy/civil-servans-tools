"""计时器数据模型（简洁版）。"""

from dataclasses import dataclass, field


@dataclass
class LapEntry:
    """单条分段记录。"""
    index: int           # 序号 #1, #2, ...
    elapsed: int         # 该分段时已用秒数


@dataclass
class TimerState:
    """计时器状态。"""
    mode: str = "countup"          # "countup" | "countdown"
    total_seconds: int = 0         # 倒计时目标秒数
    elapsed_seconds: int = 0       # 已过秒数
    is_running: bool = False
    laps: list[LapEntry] = field(default_factory=list)
