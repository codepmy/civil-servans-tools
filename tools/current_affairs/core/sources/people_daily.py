"""人民网 · 时政频道 数据源。"""

from __future__ import annotations

from .base import BaseNewsSource


class PeopleDailySource(BaseNewsSource):
    """人民网时政要闻列表。"""

    source_id = "people_daily"
    source_name = "人民网"
    list_url = "http://politics.people.com.cn/"
    # 文章链接形如 /n1/2025/0115/c1001-xxxxx.html
    url_hints = ("/n1/",)
    min_title_len = 10
    max_items = 40
