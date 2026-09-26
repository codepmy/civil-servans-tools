"""对比源 PDF 与转换结果的正文内容, 定位丢失片段。

做法: 把两份文本归一化(去空白)后, 用 10 字滑动窗口检查源文本的每个位置
是否能在结果里找到。连续找不到的区间就是丢失的内容。

页眉/页脚/水印属于刻意过滤的噪音, 先剔除再比对。

用法:
    python tools/pdf_converter/dev/diff_content.py <源.pdf> <转换后.pdf>
"""

import os
import re
import sys

import fitz

# 刻意过滤掉的噪音: 粉笔/华图页眉页脚, 页码, 水印
NOISE_PATTERNS = (
    re.compile(r"^·?\s*本试卷由"),
    re.compile(r"^第\s*\d+\s*页[，,]\s*共\s*\d+\s*页$"),
    re.compile(r"^-\s*\d+\s*-$"),
    re.compile(r"^\d+\s*/\s*\d+$"),
)
# 页眉在页面顶部的固定位置出现, 内容短且重复
HEADER_BAND_MM = 28.0


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text)


def source_body(path: str) -> str:
    """源 PDF 的正文(剔除页眉页脚带与噪音行)。"""
    parts: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            height_mm = page.rect.height * 25.4 / 72
            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
                y0_mm = y0 * 25.4 / 72
                y1_mm = y1 * 25.4 / 72
                if y1_mm <= HEADER_BAND_MM or y0_mm >= min(270.0, height_mm - 12):
                    continue
                if any(p.match(text.strip()) for p in NOISE_PATTERNS):
                    continue
                parts.append(text)
    return normalized("".join(parts))


def output_body(path: str) -> str:
    with fitz.open(path) as doc:
        return normalized("".join(page.get_text() for page in doc))


def collect_units(src: str) -> tuple[list[str], list[str]]:
    """从源文本提取内容单元: 连续中文串 + 数字串。

    不按位置比对, 因此不受"题号从题干后移到题干前"这类重排影响。
    """
    cjk = [u for u in re.findall(r"[一-鿿]{6,}", src)]
    numbers = [u for u in re.findall(r"\d+(?:\.\d+)?[%％]?", src) if len(u) >= 3]
    return cjk, numbers


def is_reorder_artifact(unit: str, out: str) -> bool:
    """判断片段是否为"重排拼接"的伪影而非真丢失。

    题号在源文件中排在题干之后, 转换后移到题干之前, 于是原文里相邻的
    "…14.5%下列选项…" 在结果中变成 "…14.5%" + "5.下列选项…"。这类片段
    拆开后每一部分都还在, 只是顺序变了。
    """
    for cut in range(1, len(unit) - 1):
        if unit[:cut] in out and unit[cut:] in out:
            return True
    return False


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    src_path, out_path = sys.argv[1], sys.argv[2]
    src = source_body(src_path)
    out = output_body(out_path)
    print(f"源正文字符: {len(src)}   转换结果字符: {len(out)}")

    cjk, numbers = collect_units(src)
    lost_cjk = [u for u in cjk if u not in out]
    lost_numbers = [u for u in numbers if u not in out]
    artifacts = [u for u in lost_cjk + lost_numbers if is_reorder_artifact(u, out)]
    missing_cjk = [u for u in lost_cjk if u not in artifacts]
    missing_numbers = [u for u in lost_numbers if u not in artifacts]

    print(f"\n中文片段: {len(cjk)} 个 | 数字串: {len(numbers)} 个")
    print(f"重排伪影(拆开后各部分俱在): {len(artifacts)} 个")
    print(f"\n真实丢失的中文片段: {len(missing_cjk)} 个")
    for unit in missing_cjk:
        print(f"  ✗ {unit[:70]}")
    print(f"真实丢失的数字串: {len(missing_numbers)} 个")
    for unit in missing_numbers[:30]:
        print(f"  ✗ {unit}")

    total = len(cjk) + len(numbers)
    missing = len(missing_cjk) + len(missing_numbers)
    print(f"\n内容单元总数 {total}, 真实丢失 {missing} ({missing / max(1, total) * 100:.2f}%)")


if __name__ == "__main__":
    main()
