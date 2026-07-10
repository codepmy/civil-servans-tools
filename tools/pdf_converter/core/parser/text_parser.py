"""Text PDF parser based on PyMuPDF."""

import io
import re
from typing import Callable

import fitz

from tools.pdf_converter.core.models import ParsedDocument, ParsedPage, TextBlock, ImageBlock
from tools.pdf_converter.core.parser.base import BaseParser

AD_KEYWORDS = [
    "关注", "公众号", "扫码", "二维码", "微信号", "微信",
    "QQ群", "QQ", "客服", "咨询", "报名", "免费领取",
    "每日一练", "每日图推", "速算", "花生十三", "粉笔",
    "华图", "中公", "腰果", "步知",
]

HEADER_CUTOFF_MM = 28.0
FOOTER_START_MM = 270.0
HEADER_CUTOFF_PT = HEADER_CUTOFF_MM * 72 / 25.4
FOOTER_START_PT = FOOTER_START_MM * 72 / 25.4
QUESTION_NUM_RE = re.compile(r"^\s*\d+\s*[\.．、。]")
SECTION_RE = re.compile(r"^[一二三四五六七八九十]+[\.．、。]\s*")
FOOTER_CONTENT_RE = re.compile(r"^(?:第\s*[一二三四五六七八九十百两0-9\d]+\s*(?:大)?题|作答要求|给定(?:资料|材料)|材料\s*\d*)")


class TextParser(BaseParser):
    """Parser for text-based PDFs."""

    def __init__(self):
        self._doc = None

    def can_handle(self, path: str) -> bool:
        return TextParser.detect_pdf_type(path) == "text"

    def parse(self, path: str, progress: Callable[[int, str], None] = None) -> ParsedDocument:
        self._doc = fitz.open(path)
        pages = []
        total = self._doc.page_count
        metadata = {
            "title": self._doc.metadata.get("title", ""),
            "author": self._doc.metadata.get("author", ""),
            "page_count": total,
            "file_path": path,
        }
        for i in range(total):
            if progress:
                progress(int((i + 1) / total * 100), "文本提取")
            pages.append(self._parse_page(self._doc[i], i))
        self._doc.close()
        return ParsedDocument(pages=pages, metadata=metadata, source_type="text")

    def _parse_page(self, page: fitz.Page, page_index: int) -> ParsedPage:
        page_dict = page.get_text("dict")
        page_rect = page.rect
        width_mm = page_rect.width * 25.4 / 72
        height_mm = page_rect.height * 25.4 / 72
        blocks = []

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                line_bbox = line.get("bbox", (0, 0, 0, 0))
                line_y0 = line_bbox[1] * 25.4 / 72
                keep_header_line = self._is_content_line_near_header(line_text, line_y0)
                keep_footer_line = self._is_content_line_near_footer(line_text, line_y0, height_mm)
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    bbox_pt = span["bbox"]
                    x0 = bbox_pt[0] * 25.4 / 72
                    y0 = bbox_pt[1] * 25.4 / 72
                    x1 = bbox_pt[2] * 25.4 / 72
                    y1 = bbox_pt[3] * 25.4 / 72
                    if y1 > min(FOOTER_START_MM, height_mm - 12):
                        if not keep_footer_line:
                            continue
                    if y0 < HEADER_CUTOFF_MM and not keep_header_line:
                        continue
                    blocks.append(TextBlock(
                        text=text,
                        bbox=(x0, y0, x1, y1),
                        font_name=span.get("font", ""),
                        font_size=span.get("size", 0),
                        is_bold=bool(span.get("flags", 0) & 2**3),
                        page_number=page_index + 1,
                    ))

        return ParsedPage(
            blocks=blocks,
            images=self._extract_visual_blocks(page, page_rect, page_index),
            page_number=page_index + 1,
            width_mm=width_mm,
            height_mm=height_mm,
        )

    @staticmethod
    def _is_content_line_near_header(text: str, y_mm: float) -> bool:
        if y_mm < 18.0:
            return False
        return bool(QUESTION_NUM_RE.match(text) or SECTION_RE.match(text))

    @staticmethod
    def _is_content_line_near_footer(text: str, y_mm: float, page_height_mm: float) -> bool:
        if y_mm > page_height_mm - 12.0:
            return False
        return bool(FOOTER_CONTENT_RE.match(text or ""))

    def _extract_visual_blocks(self, page: fitz.Page, page_rect: fitz.Rect,
                               page_index: int) -> list[ImageBlock]:
        rects: list[fitz.Rect] = []
        page_area = page_rect.get_area()
        try:
            seen = set()
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                if xref in seen:
                    continue
                seen.add(xref)
                for rect in page.get_image_rects(xref):
                    self._append_reasonable_rect(rects, rect, page_rect, page_area)
        except Exception:
            pass

        try:
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") == 1 and "bbox" in block:
                    self._append_reasonable_rect(rects, fitz.Rect(block["bbox"]), page_rect, page_area)
        except Exception:
            pass

        try:
            drawing_rects = []
            for drawing in page.get_drawings():
                rect = drawing.get("rect")
                if rect:
                    r = fitz.Rect(rect)
                    if r.width > 8 or r.height > 8:
                        drawing_rects.append(fitz.Rect(r.x0 - 1.5, r.y0 - 1.5, r.x1 + 1.5, r.y1 + 1.5))
            rects.extend(self._merge_rects(drawing_rects, page_rect, gap=10))
        except Exception:
            pass

        result = self._render_rects(page, page_rect, page_index, rects)
        if not result:
            result = self._extract_regions_by_erasing_text(page, page_rect, page_index)
        return result

    @staticmethod
    def _append_reasonable_rect(rects: list[fitz.Rect], rect: fitz.Rect,
                                page_rect: fitz.Rect, page_area: float) -> None:
        r = fitz.Rect(rect) & page_rect
        if r.is_empty or r.width <= 0 or r.height <= 0:
            return
        if r.get_area() >= page_area * 0.35:
            return
        rects.append(r)

    def _render_rects(self, page: fitz.Page, page_rect: fitz.Rect, page_index: int,
                      rects: list[fitz.Rect]) -> list[ImageBlock]:
        result: list[ImageBlock] = []
        page_area = page_rect.get_area()
        for rect in self._merge_rects(rects, page_rect, gap=4):
            if rect.y0 < HEADER_CUTOFF_PT or rect.y1 > min(FOOTER_START_PT, page_rect.height - 34):
                continue
            if rect.width > page_rect.width * 0.92 and rect.height > page_rect.height * 0.65:
                continue
            if rect.get_area() > page_area * 0.45:
                continue
            if rect.width < 24 or rect.height < 8 or rect.get_area() < 350:
                continue
            try:
                result.append(self._render_clip(page, page_rect, page_index, rect))
            except Exception:
                continue
        return result

    def _extract_regions_by_erasing_text(self, page: fitz.Page, page_rect: fitz.Rect,
                                         page_index: int) -> list[ImageBlock]:
        try:
            from PIL import Image, ImageDraw
        except Exception:
            return []

        scale = 2
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        draw = ImageDraw.Draw(image)
        width, height = image.size
        draw.rectangle((0, 0, width, int(HEADER_CUTOFF_PT * scale)), fill="white")
        footer_y = min(FOOTER_START_PT, page_rect.height - 34)
        draw.rectangle((0, int(footer_y * scale), width, height), fill="white")

        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                bbox = line.get("bbox")
                if not bbox:
                    continue
                x0, y0, x1, y1 = bbox
                draw.rectangle((
                    max(0, int(x0 * scale) - 3), max(0, int(y0 * scale) - 3),
                    min(width, int(x1 * scale) + 3), min(height, int(y1 * scale) + 3),
                ), fill="white")

        gray = image.convert("L")
        px = gray.load()
        row_counts = [sum(1 for x in range(0, width, 2) if px[x, y] < 242) for y in range(height)]
        row_groups = self._groups_from_counts(row_counts, max(10, int(width * 0.012)), max_gap=8)
        rects: list[fitz.Rect] = []
        for y0, y1 in row_groups:
            if y1 - y0 < 18:
                continue
            col_counts = []
            for x in range(width):
                col_counts.append(sum(1 for y in range(y0, y1 + 1, 2) if px[x, y] < 242))
            for x0, x1 in self._groups_from_counts(col_counts, max(8, int((y1 - y0) * 0.018)), max_gap=12):
                if x1 - x0 < 36:
                    continue
                rect = fitz.Rect(x0 / scale, y0 / scale, x1 / scale, y1 / scale)
                if rect.get_area() < 300 or rect.get_area() > page_rect.get_area() * 0.35:
                    continue
                if rect.width > page_rect.width * 0.92 and rect.height > page_rect.height * 0.65:
                    continue
                rects.append(rect)
        merged = self._merge_rects(rects, page_rect, gap=18)
        return self._render_rects(page, page_rect, page_index, merged)

    def _render_clip(self, page: fitz.Page, page_rect: fitz.Rect, page_index: int,
                     rect: fitz.Rect) -> ImageBlock:
        clip = fitz.Rect(
            max(page_rect.x0, rect.x0 - 2), max(page_rect.y0, rect.y0 - 2),
            min(page_rect.x1, rect.x1 + 2), min(page_rect.y1, rect.y1 + 2),
        )
        img_bytes = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False).tobytes("png")
        x0 = clip.x0 * 25.4 / 72
        y0 = clip.y0 * 25.4 / 72
        x1 = clip.x1 * 25.4 / 72
        y1 = clip.y1 * 25.4 / 72
        return ImageBlock(
            image_bytes=img_bytes,
            image_ext="png",
            bbox=(x0, y0, x1, y1),
            page_number=page_index + 1,
            width_mm=x1 - x0,
            height_mm=y1 - y0,
            orig_page_h_mm=page_rect.height * 25.4 / 72,
        )

    @staticmethod
    def _groups_from_counts(counts: list[int], threshold: int, max_gap: int) -> list[tuple[int, int]]:
        groups = []
        start = None
        last = None
        for idx, count in enumerate(counts):
            if count >= threshold:
                if start is None:
                    start = idx
                last = idx
            elif start is not None and last is not None and idx - last > max_gap:
                groups.append((start, last))
                start = None
                last = None
        if start is not None and last is not None:
            groups.append((start, last))
        return groups

    @staticmethod
    def _merge_rects(rects: list[fitz.Rect], page_rect: fitz.Rect, gap: float = 6) -> list[fitz.Rect]:
        clean = []
        page_area = page_rect.get_area()
        for rect in rects:
            r = fitz.Rect(rect) & page_rect
            if (not r.is_empty and r.width > 0 and r.height > 0
                    and r.get_area() < page_area * 0.6):
                clean.append(r)
        clean.sort(key=lambda r: (r.y0, r.x0))
        merged: list[fitz.Rect] = []
        for rect in clean:
            expanded = fitz.Rect(rect.x0 - gap, rect.y0 - gap, rect.x1 + gap, rect.y1 + gap)
            for idx, existing in enumerate(merged):
                horizontal_overlap = min(rect.x1, existing.x1) - max(rect.x0, existing.x0)
                vertical_overlap = min(rect.y1, existing.y1) - max(rect.y0, existing.y0)
                min_width = max(1, min(rect.width, existing.width))
                min_height = max(1, min(rect.height, existing.height))
                related = (
                    expanded.intersects(existing)
                    or (horizontal_overlap / min_width > 0.45 and abs(rect.y0 - existing.y1) < gap)
                    or (vertical_overlap / min_height > 0.45 and abs(rect.x0 - existing.x1) < gap)
                )
                if related:
                    merged[idx] = existing | rect
                    break
            else:
                merged.append(rect)
        return merged

    @staticmethod
    def detect_pdf_type(path: str) -> str:
        try:
            doc = fitz.open(path)
            total_chars = sum(len(page.get_text().strip()) for page in doc)
            avg = total_chars / max(doc.page_count, 1)
            doc.close()
            return "text" if avg > 20 else "image"
        except Exception:
            return "image"


def is_likely_ad(text: str, font_size: float = 10, x_mm: float = 0, y_mm: float = 0,
                 page_height_mm: float = 297, page_width_mm: float = 210) -> bool:
    if font_size < 8 and (y_mm < 15 or y_mm > page_height_mm - 15):
        return True
    is_corner = (x_mm < 20 or x_mm > page_width_mm - 40) and (y_mm < 20 or y_mm > page_height_mm - 20)
    text_lower = text.lower()
    for kw in AD_KEYWORDS:
        if (kw in text_lower or kw in text) and (is_corner or font_size < 9):
            return True
    return "二维码" in text or "扫码" in text or "QR" in text.upper()
