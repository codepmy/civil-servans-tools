"""时政新闻数据模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# 分类常量
CATEGORY_POLICY = "政策文件"      # 政府网政策文件
CATEGORY_NEWS = "时政要闻"        # 常规时政要闻
CATEGORY_SPEECH = "重要讲话"      # 领导人讲话/会议
CATEGORY_OTHER = "其他"

ALL_CATEGORIES = (CATEGORY_NEWS, CATEGORY_POLICY, CATEGORY_SPEECH, CATEGORY_OTHER)

CATEGORY_LABELS: dict[str, str] = {
    CATEGORY_POLICY: "政策文件",
    CATEGORY_NEWS: "时政要闻",
    CATEGORY_SPEECH: "重要讲话",
    CATEGORY_OTHER: "其他",
}


class NewsItem(BaseModel):
    """一条时政新闻。

    - ``title`` 标题
    - ``url`` 原文链接
    - ``source`` 来源 id（gov_cn / xinhua / people_daily）
    - ``source_name`` 来源显示名（中国政府网 / 新华网 / 人民网）
    - ``category`` 分类（政策文件 / 时政要闻 / 重要讲话 / 其他）
    - ``published_at`` 发布时间字符串（YYYY-MM-DD，尽力而为）
    - ``summary`` 摘要/导语
    - ``content`` 内嵌阅读正文（抓取成功后缓存）
    - ``tags`` 考点标记（会议/文件/外交/经济……）
    - ``favorited`` 是否已收藏（会话内标记，持久化以收藏列表为准）
    """

    title: str
    url: str
    source: str = ""
    source_name: str = ""
    category: str = CATEGORY_NEWS
    published_at: str = ""
    summary: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    favorited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsItem":
        return cls.model_validate(data)

    @property
    def display_meta(self) -> str:
        """列表/详情区显示的来源·时间元信息。"""
        parts = [self.source_name or self.source]
        if self.published_at:
            parts.append(self.published_at)
        return " · ".join(parts)
