"""数据源抽象基类与通用列表解析工具。

设计原则：
- 每个来源实现 ``fetch()`` 返回 ``list[NewsItem]``
- 只抓列表页（标题/链接/时间），正文由 ``core.reader`` 单独抓取
- 单个来源失败抛出 ``SourceError``，由 ``NewsFetcher`` 捕获降级，不影响其他来源
- requests / beautifulsoup4 采用延迟导入：依赖缺失时应用仍可启动，
  仅本功能报错并给出安装提示
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from ..models import CATEGORY_NEWS, NewsItem

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_REQUEST_TIMEOUT = 10

# 常见导航/无效链接文本（标题过滤用）
_SKIP_TITLE_KEYWORDS = (
    "首页", "更多", "登录", "注册", "无障碍", "网站地图", "联系我们",
    "移动版", "客户端", "微信公众号", "微博", "关于我们", "版权声明",
    "法律声明", "中国政府网", "国务院", "新华社", "人民网", "返回顶部",
    "English", "RSS", "设为首页", "加入收藏",
)

_DATE_RE = re.compile(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class SourceError(Exception):
    """单来源抓取失败。"""


class BaseNewsSource:
    """时政新闻来源抽象基类。

    子类只需声明类属性并在必要时覆写 ``_make_item``。
    """

    source_id: str = ""
    source_name: str = ""
    category: str = CATEGORY_NEWS
    list_url: str = ""
    #: URL 提示词：命中任意一个才保留该链接（空元组 = 不限制）
    url_hints: tuple[str, ...] = ()
    #: 标题最短长度（过滤导航链接）
    min_title_len: int = 10
    #: 每源最多条目数
    max_items: int = 40

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def fetch(self) -> list[NewsItem]:
        """抓取并解析列表页。失败抛 SourceError。"""
        if not self.list_url:
            raise SourceError(f"{self.source_name} 未配置列表页地址")
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise SourceError(
                f"{self.source_name} 缺少依赖 beautifulsoup4，"
                "请运行 setup.bat 或 pip install -r requirements.txt"
            ) from exc
        text = self._get_text(self.list_url)
        soup = BeautifulSoup(text, "html.parser")
        links = self._collect_links(soup)
        items: list[NewsItem] = []
        for title, url, date in links:
            item = self._make_item(title, url, date)
            if item is not None:
                items.append(item)
        if not items:
            raise SourceError(f"{self.source_name} 列表页解析结果为空（页面结构可能已改版）")
        return items

    # ------------------------------------------------------------------
    # 可覆写的钩子
    # ------------------------------------------------------------------

    def _make_item(self, title: str, url: str, date: str) -> NewsItem:
        return NewsItem(
            title=title,
            url=url,
            source=self.source_id,
            source_name=self.source_name,
            category=self.category,
            published_at=date,
        )

    # ------------------------------------------------------------------
    # 通用工具
    # ------------------------------------------------------------------

    def _get_text(self, url: str, timeout: int = _REQUEST_TIMEOUT) -> str:
        """请求网页并返回解码后的文本。"""
        try:
            import requests
        except ImportError as exc:
            raise SourceError(
                f"{self.source_name} 缺少依赖 requests，"
                "请运行 setup.bat 或 pip install -r requirements.txt"
            ) from exc
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SourceError(f"{self.source_name} 请求失败：{exc}") from exc
        # 编码兜底：部分站点响应头缺 charset
        if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def _collect_links(self, soup: BeautifulSoup) -> list[tuple[str, str, str]]:
        """收集标题链接：(title, absolute_url, date)。

        通用策略：遍历所有 <a>，按标题长度/中文字符/URL 提示过滤，
        时间从锚点向上最多 4 层的文本里用正则提取。
        """
        seen: set[str] = set()
        collected: list[tuple[str, str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            title = anchor.get_text(" ", strip=True)
            if not self._valid_title(title):
                continue
            if self.url_hints and not any(hint in href for hint in self.url_hints):
                continue
            if href.startswith(("javascript:", "mailto:", "#", "tel:")):
                continue
            absolute = urljoin(self.list_url, href)
            if absolute in seen:
                continue
            seen.add(absolute)
            collected.append((title, absolute, self._find_date(anchor)))
            if len(collected) >= self.max_items:
                break
        return collected

    def _valid_title(self, title: str) -> bool:
        """标题过滤：够长、含中文、非导航文本。"""
        if not title or len(title) < self.min_title_len:
            return False
        if not _CJK_RE.search(title):
            return False
        for keyword in _SKIP_TITLE_KEYWORDS:
            if title == keyword or title.startswith(keyword + " "):
                return False
        return True

    @staticmethod
    def _find_date(anchor) -> str:
        """从锚点及其祖先文本中提取日期，返回 YYYY-MM-DD 或空串。"""
        node = anchor
        for _ in range(4):
            if node is None:
                break
            text = node.get_text(" ", strip=True)
            match = _DATE_RE.search(text)
            if match:
                y, m, d = match.groups()
                return f"{y}-{int(m):02d}-{int(d):02d}"
            node = getattr(node, "parent", None)
        return ""
