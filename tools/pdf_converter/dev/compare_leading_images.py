"""回归脚本: 对比"共享材料图排在题干之前"改动前后的排版差异。

用法:
    python tools/pdf_converter/dev/compare_leading_images.py <pdf> [<pdf> ...]

做法: 同一份 PDF 跑两次排版 —— 一次把 _split_leading_images 打桩成
"全部归入题干之后"(改动前的行为), 一次用真实实现(改动后)。逐元素对比,
输出差异条数与明细, 用于确认改动只影响"题干前的材料图", 不波及其它题型。

退出码非 0 表示存在差异(便于在 CI/批处理里当门禁用)。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.pdf_converter.config.settings import load_template
from tools.pdf_converter.core.cleaner.xingce_cleaner import XingceCleaner
from tools.pdf_converter.core.generator.font_manager import FontManager
from tools.pdf_converter.core.layout.engine import LayoutEngine, LayoutConfig
from tools.pdf_converter.core.parser.text_parser import TextParser

FontManager().register_all()  # 排版要用 reportlab 量文字宽度, 先注册系统字体


def render(path: str, legacy: bool) -> list[tuple]:
    """跑一遍排版, 返回逐元素摘要。legacy=True 时模拟改动前的行为。"""
    parsed = TextParser().parse(path)
    cleaned = XingceCleaner().clean(parsed)
    config = LayoutConfig.from_template(load_template("xingce"), {})
    ignored = set(cleaned.ignored_pages)
    images = [
        img for pg in parsed.pages if pg.page_number not in ignored for img in pg.images
    ]

    # 取类字典里的原始描述符: 直接写 LayoutEngine._split_leading_images 会被
    # 拆包成普通函数, 赋回去就成了绑定方法(多收一个 self)
    original = LayoutEngine.__dict__["_split_leading_images"]
    if legacy:
        # 改动前: 题干之前的图也当普通插图, 一律排在题干之后
        LayoutEngine._split_leading_images = staticmethod(lambda q, imgs: ([], list(imgs)))
    try:
        engine = LayoutEngine(config)
        laid_out = engine.layout(cleaned, images=images)
        engine.finish()
    finally:
        LayoutEngine._split_leading_images = original

    summary: list[tuple] = []
    for page in laid_out.pages:
        for el in sorted(page.elements, key=lambda e: (round(e.y_mm, 1), e.x_mm)):
            if el.type == "image":
                desc = f"图 {el.image_w_mm:.1f}x{el.image_h_mm:.1f}"
            else:
                desc = (el.text or "")[:34]
            summary.append((page.page_number, el.type, desc, round(el.x_mm, 1), round(el.y_mm, 1)))
    return summary


def compare(path: str) -> int:
    name = os.path.basename(path)
    before = render(path, legacy=True)
    after = render(path, legacy=False)
    print(f"\n{'=' * 72}\n{name}\n{'=' * 72}")
    print(f"元素数: 改动前 {len(before)}  改动后 {len(after)}")

    if before == after:
        print("无差异")
        return 0

    import difflib

    diffs = [
        line for line in difflib.unified_diff(
            [f"p{p} {t} @({x},{y}) {d}" for p, t, d, x, y in before],
            [f"p{p} {t} @({x},{y}) {d}" for p, t, d, x, y in after],
            "改动前", "改动后", lineterm="", n=1,
        )
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    ]
    print(f"差异行数: {len(diffs)}")
    for line in diffs[:60]:
        print("  " + line)
    return 1


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python compare_leading_images.py <pdf> [<pdf> ...]")
        raise SystemExit(1)
    changed = sum(compare(p) for p in sys.argv[1:])
    print(f"\n有差异的文件数: {changed}/{len(sys.argv) - 1}")


if __name__ == "__main__":
    main()
