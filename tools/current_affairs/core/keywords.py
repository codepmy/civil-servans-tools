"""考点关键词标记：根据标题/正文自动标记可能考点。"""

from __future__ import annotations

import re

# 考点标签 → 关键词列表
TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "会议": (
        "会议", "全会", "大会", "座谈会", "研讨会", "论坛", "中央经济工作会议",
        "政治局", "常委会", "全体会议", "扩大会议", "双周协商",
    ),
    "讲话": (
        "重要讲话", "发表讲话", "演讲", "致辞", "贺信", "回信", "批示",
        "强调", "指出", "主持召开", "作出重要指示",
    ),
    "文件": (
        "印发", "通知", "意见", "方案", "规划", "纲要", "条例", "规定",
        "办法", "决定", "批复", "公告", "政策",
    ),
    "外交": (
        "访问", "会见", "会谈", "出访", "外交", "大使", "国际", "全球",
        "一带一路", "合作", "签署", "峰会",
    ),
    "经济": (
        "经济", "GDP", "财政", "金融", "货币", "投资", "消费", "就业",
        "物价", "增长", "税收", "央行", "利率", "外贸",
    ),
    "科技": (
        "科技", "创新", "人工智能", "芯片", "航天", "探月", "卫星",
        "量子", "5G", "数字经济", "新质生产力",
    ),
    "生态": (
        "生态", "环境", "双碳", "碳中和", "碳达峰", "绿色", "污染",
        "新能源", "气候变化", "生物多样性",
    ),
    "法治": (
        "法治", "法律", "立法", "司法", "宪法", "执法", "条例", "依法",
    ),
    "民生": (
        "养老", "医疗", "教育", "社保", "住房", "就业", "医保", "生育",
        "托育", "粮食", "应急",
    ),
    "乡村振兴": (
        "乡村", "农业", "农村", "振兴", "粮食安全", "耕地", "脱贫",
    ),
    "改革开放": (
        "改革", "开放", "自贸区", "营商环境", "民营经济", "扩大开放",
    ),
}

_TAG_RE: dict[str, re.Pattern] = {
    tag: re.compile("|".join(re.escape(k) for k in keywords))
    for tag, keywords in TAG_KEYWORDS.items()
}

MAX_TAGS = 3


def mark_tags(title: str, summary: str = "", content: str = "") -> list[str]:
    """扫描标题/摘要/正文，返回命中的考点标签（最多 MAX_TAGS 个）。

    按标签字典序输出，保证结果稳定。
    """
    text = f"{title} {summary} {content}"
    if not text.strip():
        return []
    matched: list[str] = []
    for tag, pattern in sorted(_TAG_RE.items()):
        if pattern.search(text):
            matched.append(tag)
        if len(matched) >= MAX_TAGS:
            break
    return matched


def refine_category(title: str, source_id: str) -> str:
    """根据标题与来源修正分类。"""
    from .models import CATEGORY_NEWS, CATEGORY_OTHER, CATEGORY_POLICY, CATEGORY_SPEECH

    if source_id == "gov_cn":
        return CATEGORY_POLICY
    if "重要讲话" in title or ("讲话" in title and "习近平" in title):
        return CATEGORY_SPEECH
    if title.strip():
        return CATEGORY_NEWS
    return CATEGORY_OTHER
