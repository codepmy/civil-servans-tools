"""新华网 · 时政频道 数据源。"""

from __future__ import annotations

from .base import BaseNewsSource


class XinhuaSource(BaseNewsSource):
    """新华网时政要闻列表。"""

    source_id = "xinhua"
    source_name = "新华网"
    list_url = "https://www.news.cn/politics/"
    # 文章链接形如 /politics/2025-01/15/c_xxxxx.htm
    url_hints = ("/politics/",)
    min_title_len = 12
    max_items = 40
