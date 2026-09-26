"""对照实验: 同一份 PDF 分别在"启用/禁用 开头材料收集"下清洗, 对比题号。

用于确认 _extract_questions 的 collect_leading_material 改动是否影响题号识别。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.pdf_converter.core.parser.text_parser import TextParser
from tools.pdf_converter.core.cleaner.xingce_cleaner import XingceCleaner


def run(path: str, enable: bool):
    parsed = TextParser().parse(path)
    cleaner = XingceCleaner()
    original = XingceCleaner._extract_questions

    def forced(self, lines, collect_leading_material=False, _orig=original, _enable=enable):
        return _orig(self, lines, collect_leading_material=_enable)

    XingceCleaner._extract_questions = forced
    try:
        cleaned = cleaner.clean(parsed)
    finally:
        XingceCleaner._extract_questions = original
    return cleaned


def main() -> None:
    for path in sys.argv[1:]:
        print(f"\n{'=' * 70}\n{os.path.basename(path)}\n{'=' * 70}")
        for enable in (False, True):
            cleaned = run(path, enable)
            nums = [q.number for q in cleaned.questions]
            sections = sum(1 for q in cleaned.questions if getattr(q, "section_heading", ""))
            chars = sum(len(q.stem) + sum(len(o.text) for o in q.options) for q in cleaned.questions)
            sec_chars = sum(len(str(getattr(q, "section_heading", ""))) for q in cleaned.questions)
            label = "启用" if enable else "禁用"
            print(f"  [{label}开头材料] 题{len(cleaned.questions)} 带材料{sections} "
                  f"正文{chars}字 材料{sec_chars}字")
            print(f"      题号: {nums}")


if __name__ == "__main__":
    main()
