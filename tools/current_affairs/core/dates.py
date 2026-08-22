"""日期辅助工具（本地时区）。"""

from __future__ import annotations

from datetime import datetime, timedelta

_WEEKDAY_CN = "一二三四五六日"


def today_str() -> str:
    """今天日期，格式 YYYY-MM-DD。"""
    return datetime.now().strftime("%Y-%m-%d")


def now_iso() -> str:
    """当前时间 ISO 字符串（用于缓存时间戳）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_days(date_str: str, delta: int) -> str:
    """日期加减 N 天，返回 YYYY-MM-DD。"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return today_str()
    return (d + timedelta(days=delta)).strftime("%Y-%m-%d")


def weekday_cn(date_str: str) -> str:
    """返回「周一」~「周日」。"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return ""
    return "周" + _WEEKDAY_CN[d.weekday()]


def display_date(date_str: str) -> str:
    """展示用日期：YYYY-MM-DD（周X）。"""
    wd = weekday_cn(date_str)
    return f"{date_str}（{wd}）" if wd else date_str


def is_stale(timestamp: str, hours: float = 6.0) -> bool:
    """判断时间戳是否已超过 N 小时（过期需刷新）。"""
    if not timestamp:
        return True
    try:
        ts = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return (datetime.now() - ts).total_seconds() > hours * 3600
