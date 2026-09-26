"""对比图片归属逻辑改动前后的差异。

用 monkeypatch 把 LayoutEngine 还原成"本次改动前"的两个行为:
  1. _group_images 按 -bbox[1] 降序排(错误的坐标系假设) -> 同页多图顺序颠倒
  2. _take_images_for_question 不做"上一题末行"的起点放宽/终点收紧
然后逐份试卷打印图片元素序列, 对比图片是否丢失、顺序与归属是否变化。

用法:
    python tools/pdf_converter/dev/compare_images.py <pdf> [<pdf> ...]
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


def old_group_images(self, images):
    grouped: dict[int, list] = {}
    for img in images:
        grouped.setdefault(img.page_number, []).append(img)
    for page_images in grouped.values():
        page_images.sort(key=lambda i: (-i.bbox[1], i.bbox[0]))
    return grouped


def old_take_images_for_question(self, question):
    """改动前的取图范围: 不做"上一题末行"的起点放宽 / "本题末行"的终点收紧。"""
    is_da = getattr(question, "is_data_analysis", False)
    end_y = getattr(question, "source_end_y_mm", None)
    if is_da and end_y is not None:
        end_y = end_y + 3.0
    end_page = getattr(question, "source_end_page", None) or question.source_page
    end_page_floor = None
    if end_page != question.source_page:
        page_first = (self._page_questions.get(end_page) or [None])[0]
        if page_first is not None and page_first is not question:
            end_page_floor = getattr(page_first, "source_y_mm", 0) or 0
    return self._take_images_in_source_range(
        start_page=question.source_page,
        start_y=getattr(question, "source_y_mm", 0) or 0,
        end_page=end_page,
        end_y=end_y,
        end_page_floor=end_page_floor,
    )


_ORIG_GROUP = LayoutEngine._group_images
_ORIG_TAKE = LayoutEngine._take_images_for_question


def image_digest(laid) -> list[str]:
    """按版面顺序列出所有图片元素, 附带它前面最近的题号。"""
    rows: list[str] = []
    for page in laid.pages:
        last_label = "?"
        for el in sorted(page.elements, key=lambda e: (round(e.y_mm, 1), e.x_mm)):
            if el.type == "question_number":
                last_label = (el.text or "").split(".")[0].split("、")[0].strip() or "?"
            elif el.type == "image":
                rows.append(f"p{page.page_number:>3} y={el.y_mm:6.1f} "
                            f"{el.image_w_mm:6.1f}x{el.image_h_mm:5.1f}mm  前题={last_label}")
    return rows


def run(path: str, old: bool) -> tuple[list[str], int, int, int]:
    parsed = TextParser().parse(path)
    cleaned = XingceCleaner().clean(parsed)

    if old:
        LayoutEngine._group_images = old_group_images
        LayoutEngine._take_images_for_question = old_take_images_for_question
    else:
        LayoutEngine._group_images = _ORIG_GROUP
        LayoutEngine._take_images_for_question = _ORIG_TAKE

    config = LayoutConfig.from_template(load_template("xingce"), {})
    ignored = set(cleaned.ignored_pages)
    images = [img for pg in parsed.pages if pg.page_number not in ignored for img in pg.images]
    engine = LayoutEngine(config)
    laid = engine.layout(cleaned, images=images)
    engine.finish()
    return image_digest(laid), laid.total_pages, sum(len(p.elements) for p in laid.pages), len(cleaned.questions)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    FontManager().register_all()
    for path in sys.argv[1:]:
        name = os.path.basename(path)
        old_digest, old_pages, old_elems, nq = run(path, old=True)
        new_digest, new_pages, new_elems, _ = run(path, old=False)
        print(f"\n{'=' * 76}\n{name}  ({nq} 题)\n{'=' * 76}")
        print(f"  页数 {old_pages} -> {new_pages}   元素 {old_elems} -> {new_elems}   "
              f"图片 {len(old_digest)} -> {len(new_digest)}")

        if old_digest == new_digest:
            print("  图片序列完全一致")
            continue

        import difflib
        diff = list(difflib.unified_diff(old_digest, new_digest, "改动前", "改动后", lineterm="", n=1))
        print(f"  差异 {sum(1 for d in diff if d.startswith(('+', '-')) and not d.startswith(('+++', '---')))} 行:")
        for line in diff:
            print(f"    {line}")


if __name__ == "__main__":
    main()
