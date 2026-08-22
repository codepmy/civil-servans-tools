"""多源聚合抓取器：抓取 → 去重 → 打标签 → 排序。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .keywords import mark_tags, refine_category
from .models import NewsItem
from .sources import BaseNewsSource, default_sources


@dataclass
class FetchResult:
    """一次抓取的完整结果。"""

    items: list[NewsItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    sources_ok: int = 0
    sources_total: int = 0

    @property
    def ok(self) -> bool:
        return self.sources_ok > 0 or bool(self.items)


class NewsFetcher:
    """组合多个数据源执行一次抓取。

    - 单个来源失败不影响其他来源（错误记录在 ``errors``）
    - 按 URL 去重（跨源重复保留先到者）
    - 自动打考点标签并修正分类
    - 按发布时间倒序（无时间的排在最后）
    """

    def __init__(self, sources: list[BaseNewsSource] | None = None):
        self.sources: list[BaseNewsSource] = sources or default_sources()

    def fetch_all(self) -> FetchResult:
        result = FetchResult(sources_total=len(self.sources))

        for source in self.sources:
            try:
                fetched = source.fetch()
                result.items.extend(fetched)
                result.sources_ok += 1
            except Exception as exc:  # 单源失败 → 降级，不中断整体
                result.errors.append(str(exc))

        result.items = self._finalize(result.items)
        return result

    # ------------------------------------------------------------------

    @staticmethod
    def _finalize(items: list[NewsItem]) -> list[NewsItem]:
        """去重 + 打标签 + 分类修正 + 排序。"""
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for item in items:
            key = item.url.strip().rstrip("/")
            if not key or key in seen:
                continue
            seen.add(key)
            item.category = refine_category(item.title, item.source)
            item.tags = mark_tags(item.title, item.summary)
            unique.append(item)
        unique.sort(key=lambda it: _date_key(it), reverse=True)
        return unique


def _date_key(item: NewsItem) -> tuple[int, int, int]:
    """排序键：published_at 转 (y, m, d)，无日期为 (0, 0, 0)。"""
    try:
        y, m, d = item.published_at.split("-")
        return int(y), int(m), int(d)
    except (ValueError, AttributeError):
        return 0, 0, 0
