"""中国政府网 · 最新政策 数据源。"""

from __future__ import annotations

from ..models import CATEGORY_POLICY
from .base import BaseNewsSource


class GovCnSource(BaseNewsSource):
    """国务院政策文件库「最新政策」列表。"""

    source_id = "gov_cn"
    source_name = "中国政府网"
    category = CATEGORY_POLICY
    list_url = "https://www.gov.cn/zhengce/zuixin.htm"
    # 政策文章链接形如 /zhengce/content/202501/content_xxxxx.htm
    url_hints = ("/content/",)
    min_title_len = 12
    max_items = 40
