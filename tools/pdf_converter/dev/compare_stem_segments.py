"""对比题干分段逻辑改动前后的差异, 确认只影响"并列序号独立成行"的题干。"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.pdf_converter.core.generator.font_manager import FontManager
from tools.pdf_converter.core.layout.engine import LayoutEngine
from tools.pdf_converter.core.parser.text_parser import TextParser
from tools.pdf_converter.core.cleaner.xingce_cleaner import XingceCleaner

CIRCLED = "".join(chr(c) for c in range(0x2460, 0x246A))


def old_stem_segments(text: str, section_heading: str = "") -> list[str]:
    """改动前的实现: 只对政治理论/常识判断做行内圆圈数字拆分。"""
    normalized = LayoutEngine._normalize_question_text(text)
    if not normalized:
        return [""]
    if not ("政治理论" in section_heading or "常识判断" in section_heading):
        return [normalized]
    matches = list(re.finditer(f"[{re.escape(CIRCLED)}]", normalized))
    if not matches:
        return [normalized]
    segments: list[str] = []
    first_start = matches[0].start()
    if first_start > 0:
        segments.append(normalized[:first_start])
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        segments.append(normalized[match.start():end])
    return segments or [normalized]


def main() -> None:
    FontManager().register_all()
    for path in sys.argv[1:]:
        parsed = TextParser().parse(path)
        cleaned = XingceCleaner().clean(parsed)
        print(f"\n{'=' * 70}\n{os.path.basename(path)}  ({len(cleaned.questions)} 题)\n{'=' * 70}")
        changed = 0
        for q in cleaned.questions:
            heading = getattr(q, "section_heading", "") or ""
            old = old_stem_segments(q.stem, heading)
            new = LayoutEngine._stem_segments(q.stem, heading)
            if old != new:
                changed += 1
                print(f"\n第{q.number}题  [{heading.strip()[:24] or '无模块'}]")
                print(f"  原文: {q.stem[:110]!r}")
                print(f"  旧({len(old)}段): {[s[:26] for s in old[:5]]}")
                print(f"  新({len(new)}段): {[s[:26] for s in new[:5]]}")
        print(f"\n分段结果变化的题: {changed}/{len(cleaned.questions)}")


if __name__ == "__main__":
    main()
