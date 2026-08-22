"""正文抓取：从文章页提取正文纯文本（内嵌阅读）。

设计说明：
- 只为已知站点结构做尽力而为的提取，失败由 UI 兜底（提示打开浏览器）
- 通过候选正文容器选择器 + 「段落文本最长」启发式定位正文
- 去除脚本/样式/导航/页脚噪音，清洗行尾垃圾行
- requests / beautifulsoup4 延迟导入：依赖缺失只报错，不影响应用启动
"""

from __future__ import annotations

import re

from .sources.base import USER_AGENT

_REQUEST_TIMEOUT = 12

# 候选正文容器（站点 + 通用兜底）
_CONTENT_SELECTORS = (
    # 政府网：政策正文
    "div.pages_content",
    # 新华网
    "div#detail, div.main-article, div.article",
    # 人民网
    "div.rm_txt_con, div#rwb_zw, div.show_text, div.box_con",
    # 通用兜底
    "article, div.article-content, div.content, div.article_txt, div.text_con, div#ozoom",
)

# 需要整体移除的标签
_REMOVE_TAGS = ("script", "style", "noscript", "iframe", "nav", "aside", "footer", "form")

# 行尾垃圾行（以这些开头/包含的短行直接丢弃）
_JUNK_LINE_STARTS = (
    "责任编辑", "编辑：", "编辑:", "校对", "分享到", "扫一扫", "扫码",
    "来源：", "来源:", "新华社", "人民网", "新华网", "点击进入", "相关推荐",
    "X关闭", "打印", "纠错", "E-mail推荐", "客户端", "欢迎下载",
)
_JUNK_LINE_HINTS = ("广告", "热门推荐", "专题推荐", "延伸阅读")


class ArticleError(Exception):
    """正文抓取失败。"""


def fetch_article_text(url: str, timeout: int = _REQUEST_TIMEOUT) -> str:
    """抓取文章页并返回清洗后的正文纯文本。

    失败（网络/解析/内容过短）抛 ArticleError。
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ArticleError(
            "缺少网络依赖 requests / beautifulsoup4，"
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
        raise ArticleError(f"正文请求失败：{exc}") from exc

    if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in _REMOVE_TAGS:
        for node in soup.find_all(tag):
            node.decompose()

    body = _pick_content_container(soup)
    paragraphs = _extract_paragraphs(body)
    text = _join_paragraphs(paragraphs)

    if len(text) < 40:
        raise ArticleError("未能提取到有效正文（页面结构可能已改版）")
    return text


# ----------------------------------------------------------------------
# 内部实现
# ----------------------------------------------------------------------


def _pick_content_container(soup: BeautifulSoup):
    """选择正文容器：候选选择器命中里文本最长的那个；否则退回 <body>。"""
    candidates: list = []
    for selector in _CONTENT_SELECTORS:
        for node in soup.select(selector):
            candidates.append(node)
    if candidates:
        return max(candidates, key=lambda node: len(node.get_text("", strip=True)))
    return soup.body if soup.body is not None else soup


def _extract_paragraphs(container) -> list[str]:
    """优先取 <p> 段落；不足则按换行文本切分。"""
    paragraphs = [
        p.get_text(" ", strip=True)
        for p in container.find_all("p")
    ]
    cleaned = [p for p in paragraphs if _valid_paragraph(p)]
    if len("".join(cleaned)) >= 60:
        return cleaned
    # 无有效 <p> 时退回整段文本按行切分
    raw_lines = container.get_text("\n", strip=True).split("\n")
    return [line.strip() for line in raw_lines if _valid_paragraph(line.strip())]


def _valid_paragraph(text: str) -> bool:
    if len(text) < 8:
        return False
    if not re.search(r"[\u4e00-\u9fff]", text):
        return False
    if text.startswith(_JUNK_LINE_STARTS):
        return False
    if any(hint in text for hint in _JUNK_LINE_HINTS) and len(text) < 30:
        return False
    return True


def _join_paragraphs(paragraphs: list[str]) -> str:
    """合并段落并去除连续重复。"""
    seen: set[str] = set()
    parts: list[str] = []
    for para in paragraphs:
        if not para or para in seen:
            continue
        seen.add(para)
        parts.append(para)
    return "\n\n".join(parts)
