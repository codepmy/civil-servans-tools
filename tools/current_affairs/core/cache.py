"""本地缓存 / 收藏 / TXT 导出。

存储文件：``news_cache.json``
- 源码运行：项目根目录（与 user_config.json 同位置）
- 打包运行：``%APPDATA%/CivilServantsTools/news_cache.json``

结构::

    {
      "version": 1,
      "by_date": { "2025-01-15": [NewsItem dict, ...], ... },
      "updated_at": { "2025-01-15": "2025-01-15 12:00:00", ... },
      "favorites": [NewsItem dict, ...]
    }
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .dates import add_days
from .models import NewsItem

CACHE_VERSION = 1
CACHE_FILENAME = "news_cache.json"
# 按日期保留最近 N 天
KEEP_DAYS = 30


def news_cache_path() -> Path:
    """返回可写的缓存文件路径（源码/打包两种形态）。"""
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            config_dir = Path(appdata) / "CivilServantsTools"
        else:
            config_dir = Path.home() / ".civil_servants_tools"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / CACHE_FILENAME
    from app_paths import app_root

    return app_root() / CACHE_FILENAME


class NewsCache:
    """时政新闻缓存与收藏。线程安全由调用方保证（主线程使用）。"""

    def __init__(self, path: Path | None = None):
        self._path = path or news_cache_path()
        self._data = self._load()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get_day(self, date_str: str) -> list[NewsItem]:
        raw = self._data.get("by_date", {}).get(date_str, [])
        return [NewsItem.from_dict(d) for d in raw]

    def updated_at(self, date_str: str) -> str:
        return str(self._data.get("updated_at", {}).get(date_str, ""))

    def all_dates(self) -> list[str]:
        return sorted(self._data.get("by_date", {}).keys(), reverse=True)

    def favorites(self) -> list[NewsItem]:
        raw = self._data.get("favorites", [])
        return [NewsItem.from_dict(d) for d in raw]

    def is_favorite(self, url: str) -> bool:
        return any(f.url == url for f in self.favorites())

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def set_day(self, date_str: str, items: list[NewsItem]) -> None:
        from .dates import now_iso

        by_date = self._data.setdefault("by_date", {})
        by_date[date_str] = [item.to_dict() for item in items]
        self._data.setdefault("updated_at", {})[date_str] = now_iso()
        self._prune()
        self._save()

    def toggle_favorite(self, item: NewsItem) -> bool:
        """收藏/取消收藏，返回操作后的状态（True=已收藏）。"""
        favorites = self._data.setdefault("favorites", [])
        for i, fav in enumerate(favorites):
            if fav.get("url") == item.url:
                favorites.pop(i)
                self._save()
                return False
        snapshot = item.to_dict()
        snapshot["favorited"] = True
        favorites.insert(0, snapshot)
        self._save()
        return True

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def export_txt(self, date_str: str, items: list[NewsItem], path: str | Path) -> None:
        """将某日的新闻导出为 TXT（UTF-8 with BOM，兼容记事本）。"""
        lines: list[str] = [
            "=" * 46,
            "公考小工具 · 每日时政",
            f"日期：{date_str}",
            f"共 {len(items)} 条",
            "=" * 46,
            "",
        ]
        for i, item in enumerate(items, start=1):
            lines.append(f"[{i}] {item.title}")
            meta = "  ".join(
                part
                for part in (
                    f"分类：{item.category}",
                    f"来源：{item.source_name or item.source}",
                    f"时间：{item.published_at}",
                )
                if part
            )
            lines.append(f"    {meta}")
            if item.tags:
                lines.append(f"    考点：{' / '.join(item.tags)}")
            if item.summary:
                lines.append(f"    摘要：{item.summary}")
            lines.append(f"    原文：{item.url}")
            lines.append("")
        content = "\n".join(lines)
        Path(path).write_text(content, encoding="utf-8-sig")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("version") == CACHE_VERSION:
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": CACHE_VERSION, "by_date": {}, "updated_at": {}, "favorites": []}

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except OSError:
            pass  # 缓存写入失败不影响主流程

    def _prune(self) -> None:
        """只保留最近 KEEP_DAYS 天的数据。"""
        by_date = self._data.get("by_date", {})
        if len(by_date) <= KEEP_DAYS:
            return
        keep: set[str] = set()
        from .dates import today_str

        cursor = today_str()
        for _ in range(KEEP_DAYS):
            keep.add(cursor)
            cursor = add_days(cursor, -1)
        stale = [d for d in by_date if d not in keep]
        for d in stale:
            by_date.pop(d, None)
            self._data.get("updated_at", {}).pop(d, None)
