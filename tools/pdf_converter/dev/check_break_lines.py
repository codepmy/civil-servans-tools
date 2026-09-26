"""对比新旧换行算法: 统计差异行, 确认改动只影响"数字/拉丁串被断开"的情形。"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from reportlab.pdfbase.pdfmetrics import stringWidth
from tools.pdf_converter.core.generator.font_manager import FontManager
from tools.pdf_converter.core.layout.engine import LayoutEngine, LayoutConfig
from tools.pdf_converter.core.parser.text_parser import TextParser
from tools.pdf_converter.core.cleaner.xingce_cleaner import XingceCleaner


def old_break(text: str, max_width_mm: float, font_name: str, font_size: float) -> list[str]:
    """改动前的实现: 逐字符断行。"""
    text = text or ""
    if not text.strip():
        return [""]
    max_w_pt = max(max_width_mm, 5) * 72 / 25.4
    lines, cur = [], ""
    for ch in text:
        if stringWidth(cur + ch, font_name, font_size) <= max_w_pt or not cur:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [text]


def main() -> None:
    FontManager().register_all()
    texts: list[str] = []
    for path in sys.argv[1:]:
        parsed = TextParser().parse(path)
        cleaned = XingceCleaner().clean(parsed)
        for q in cleaned.questions:
            texts.append(q.stem)
            texts.extend(o.text for o in q.options)
            texts.extend(str(getattr(q, "section_heading", "")).splitlines())

    engine = LayoutEngine(LayoutConfig())
    width = engine.content_width
    font, size = "SimSun", 10.5

    changed = []
    for text in texts:
        if not text.strip():
            continue
        old = old_break(text, width, font, size)
        new = engine._break_lines(text, width, font, size)
        if old != new:
            changed.append((text, old, new))

    print(f"样本 {len(texts)} 条, 断行结果不同的 {len(changed)} 条 "
          f"({len(changed) / max(1, len(texts)) * 100:.1f}%)")
    for text, old, new in changed[:15]:
        print(f"\n原文: {text[:70]}")
        print(f"  旧: {old[:3]}")
        print(f"  新: {new[:3]}")


if __name__ == "__main__":
    main()
