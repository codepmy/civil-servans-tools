"""回归脚本: 对多份试卷跑转换, 输出统计信息用于对比改动前后是否退化。

用法:
    python tools/pdf_converter/dev/regression.py <pdf> [<pdf> ...]
"""

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.pdf_converter.core.pipeline import ConversionPipeline
from tools.pdf_converter.core.parser.text_parser import TextParser
from tools.pdf_converter.core.cleaner.xingce_cleaner import XingceCleaner
from tools.pdf_converter.config.settings import load_template
from tools.pdf_converter.core.layout.engine import LayoutEngine, LayoutConfig


def summarize(path: str) -> None:
    name = os.path.basename(path)
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    try:
        parsed = TextParser().parse(path)
    except Exception as exc:
        print(f"  [解析失败] {exc}")
        return

    image_count = sum(len(p.images) for p in parsed.pages)
    print(f"  解析: {len(parsed.pages)} 页, {image_count} 张图, 类型={parsed.source_type}")

    try:
        cleaner = XingceCleaner()
        cleaned = cleaner.clean(parsed)
    except Exception as exc:
        print(f"  [清洗失败] {exc}")
        traceback.print_exc()
        return

    print(f"  清洗: {len(cleaned.questions)} 题, 过滤 {len(cleaned.filtered_out)} 行, "
          f"答案段 {len(cleaned.answer_sections)}")
    with_section = sum(1 for q in cleaned.questions if getattr(q, "section_heading", ""))
    da_count = sum(1 for q in cleaned.questions if getattr(q, "is_data_analysis", False))
    print(f"        带材料题 {with_section}, 资料分析题 {da_count}")
    nums = [q.number for q in cleaned.questions]
    print(f"        题号: {nums[:12]}{' ...' if len(nums) > 12 else ''}")
    optionless = [q.number for q in cleaned.questions if len(q.options) not in (4,)]
    if optionless:
        print(f"        非4选项题: {optionless[:15]}")

    try:
        config = LayoutConfig.from_template(load_template("xingce"), {})
        ignored = set(cleaned.ignored_pages)
        images = [img for pg in parsed.pages if pg.page_number not in ignored for img in pg.images]
        engine = LayoutEngine(config)
        laid = engine.layout(cleaned, images=images)
        engine.finish()
        print(f"  排版: {laid.total_pages} 页, "
              f"元素 {sum(len(p.elements) for p in laid.pages)}")
    except Exception as exc:
        print(f"  [排版失败] {exc}")
        traceback.print_exc()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    pipeline = ConversionPipeline()
    for path in sys.argv[1:]:
        summarize(path)
        try:
            out = pipeline.run(path)
            print(f"  生成: OK ({len(out)} bytes)")
        except Exception as exc:
            print(f"  [生成失败] {exc}")


if __name__ == "__main__":
    main()
