"""调试脚本: 跑完整流水线并把各阶段结果 dump 到文本文件。

用法:
    python tools/pdf_converter/dev/dump_convert.py <input.pdf> [输出目录]

输出:
    out/01_parsed_pages.txt  解析阶段每页文本行(带坐标)
    out/02_cleaned.txt       清洗后的题目/材料结构
    out/03_filtered.txt      被过滤掉的行
    out/04_layout.txt        排版后的页面元素
    out/05_source_text.txt   原始 PDF 的纯文本(用于内容对比)
    out/result.pdf           转换结果
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tools.pdf_converter.core.pipeline import ConversionPipeline
from tools.pdf_converter.core.parser.text_parser import TextParser
from tools.pdf_converter.core.cleaner.xingce_cleaner import XingceCleaner


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python dump_convert.py <input.pdf> [输出目录]")
        raise SystemExit(1)

    input_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "05_source_text.txt"), "w", encoding="utf-8") as fh:
        import fitz
        with fitz.open(input_path) as src:
            for i, page in enumerate(src, start=1):
                fh.write(f"=== 源 PDF 第 {i} 页 ===\n")
                fh.write(page.get_text())
                fh.write("\n")

    parsed = TextParser().parse(input_path)
    with open(os.path.join(out_dir, "01_parsed_pages.txt"), "w", encoding="utf-8") as fh:
        for page in parsed.pages:
            fh.write(f"=== 第 {page.page_number} 页 ({page.width_mm:.0f}x{page.height_mm:.0f}mm) 图片 {len(page.images)} 张 ===\n")
            for block in sorted(page.blocks, key=lambda b: (round(b.bbox[1], 1), b.bbox[0])):
                fh.write(f"  y={block.bbox[1]:7.1f} x={block.bbox[0]:7.1f} | {block.text}\n")
            for img in page.images:
                fh.write(f"  [图片] x={img.bbox[0]:.1f} y={img.bbox[1]:.1f} {img.width_mm:.1f}x{img.height_mm:.1f}mm\n")
            fh.write("\n")

    # 包装 _extract_questions, 记录送进来的原始行序列(定位丢失点用)
    captured: dict = {}
    original_extract = XingceCleaner._extract_questions

    def capturing_extract(self, lines, *args, **kwargs):
        captured["lines"] = list(lines)
        return original_extract(self, lines, *args, **kwargs)

    XingceCleaner._extract_questions = capturing_extract
    try:
        cleaner = XingceCleaner()
        cleaned = cleaner.clean(parsed)
    finally:
        XingceCleaner._extract_questions = original_extract

    with open(os.path.join(out_dir, "06_exam_lines.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"送入题目提取的行数: {len(captured.get('lines', []))}\n\n")
        for item in captured.get("lines", []):
            if item[0] == "__SECTION__":
                fh.write(f"[SECTION] p{item[2]} y={item[3]:.1f} x={item[4]:.1f} | {item[1]}\n")
            else:
                fh.write(f"p{item[1]} y={item[2]:.1f} x={item[3]:.1f} | {item[0]}\n")

    with open(os.path.join(out_dir, "02_cleaned.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"题目总数: {len(cleaned.questions)}\n\n")
        for q in cleaned.questions:
            fh.write(f"--- 第{q.number}题 (源页{q.source_page}) ---\n")
            section = getattr(q, "section_heading", "")
            if section:
                fh.write(f"[材料/section_heading] 源页{getattr(q, 'section_source_page', '?')} "
                         f"-> 结束页{getattr(q, 'section_end_page', '?')}\n")
                for sline in str(section).splitlines():
                    fh.write(f"    | {sline}\n")
            fh.write(f"题干: {q.stem}\n")
            for opt in q.options:
                fh.write(f"  {opt.label}. {opt.text}\n")
            fh.write("\n")

    with open(os.path.join(out_dir, "03_filtered.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"过滤行数: {len(cleaned.filtered_out)}\n\n")
        for line in cleaned.filtered_out:
            fh.write(line + "\n")

    pipeline = ConversionPipeline()
    output = pipeline.run(input_path)
    with open(os.path.join(out_dir, "result.pdf"), "wb") as fh:
        fh.write(output)

    # 排版结果需要重跑一次 layout 才能拿到
    from tools.pdf_converter.config.settings import load_template
    from tools.pdf_converter.core.layout.engine import LayoutEngine, LayoutConfig
    config = LayoutConfig.from_template(load_template("xingce"), {})
    ignored = set(cleaned.ignored_pages)
    images = [img for pg in parsed.pages if pg.page_number not in ignored for img in pg.images]
    engine = LayoutEngine(config)
    laid_out = engine.layout(cleaned, images=images)
    engine.finish()
    with open(os.path.join(out_dir, "04_layout.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"排版页数: {laid_out.total_pages}\n\n")
        for page in laid_out.pages:
            fh.write(f"=== 排版第 {page.page_number} 页 ===\n")
            for el in sorted(page.elements, key=lambda e: (round(e.y_mm, 1), e.x_mm)):
                if el.type == "image":
                    fh.write(f"  y={el.y_mm:7.1f} x={el.x_mm:7.1f} [{el.type}] "
                             f"{el.image_w_mm:.1f}x{el.image_h_mm:.1f}mm src_p{getattr(el, 'source_page', '?')}\n")
                else:
                    fh.write(f"  y={el.y_mm:7.1f} x={el.x_mm:7.1f} [{el.type}] {el.text}\n")
            fh.write("\n")

    print(f"完成, 输出目录: {out_dir}")
    print(f"  题目数: {len(cleaned.questions)}  过滤行: {len(cleaned.filtered_out)}  排版页数: {laid_out.total_pages}")


if __name__ == "__main__":
    main()
