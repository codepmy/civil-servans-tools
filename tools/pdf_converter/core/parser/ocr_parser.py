"""OCR解析器: 使用PaddleOCR识别扫描/图片型PDF中的中文文字。

PaddleOCR模型会在首次使用时自动下载(约500MB)。
"""

import io
import fitz
import numpy as np
from typing import Callable

from tools.pdf_converter.core.models import ParsedDocument, ParsedPage, TextBlock
from tools.pdf_converter.core.parser.base import BaseParser


class OCRParser(BaseParser):
    """基于PaddleOCR的扫描型PDF解析器。

    适用于扫描件或图片型PDF，文字不可直接提取的场景。
    """

    def __init__(self):
        self._ocr = None

    def _get_ocr(self):
        """延迟加载OCR模型(首次使用才下载)。"""
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
                self._ocr = PaddleOCR(
                    lang='ch',
                    use_angle_cls=True,
                    show_log=False,
                )
            except ImportError:
                raise ImportError(
                    "需要安装PaddleOCR: pip install paddleocr paddlepaddle\n"
                    "注意: 首次运行会自动下载中文OCR模型(约500MB)"
                )
        return self._ocr

    def can_handle(self, path: str) -> bool:
        """OCR解析器可以处理任何PDF(作为文本解析器的回退)。"""
        return True

    def parse(self, path: str, progress: Callable[[int, str], None] = None) -> ParsedDocument:
        """使用OCR解析PDF。

        Args:
            path: PDF文件路径
            progress: 进度回调

        Returns:
            ParsedDocument
        """
        doc = fitz.open(path)
        total = doc.page_count
        pages = []

        ocr = self._get_ocr()

        for i in range(total):
            if progress:
                progress(int((i + 1) / total * 100), f"OCR识别 {i+1}/{total}")

            page = doc[i]
            parsed_page = self._ocr_page(page, i, ocr)
            pages.append(parsed_page)

        doc.close()

        return ParsedDocument(
            pages=pages,
            metadata={
                "title": "",
                "page_count": total,
                "file_path": path,
            },
            source_type="image",
        )

    def _ocr_page(self, page: fitz.Page, page_index: int, ocr) -> ParsedPage:
        """对单页执行OCR。"""
        page_rect = page.rect
        width_mm = page_rect.width * 25.4 / 72
        height_mm = page_rect.height * 25.4 / 72

        # 渲染为300 DPI图片
        pix = page.get_pixmap(dpi=300)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )

        # 如果是RGBA，转为RGB
        if img.shape[2] == 4:
            img = img[:, :, :3]

        # OCR识别
        results = ocr.ocr(img, cls=True)

        blocks = []
        if results and results[0]:
            for line_info in results[0]:
                bbox = line_info[0]  # [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
                text = line_info[1][0]  # 识别的文本
                confidence = line_info[1][1]  # 置信度

                if confidence < 0.5:  # 低置信度跳过
                    continue

                # 坐标转换: OCR坐标(px) → mm (从左上角)
                scale = 25.4 / 300  # 300 DPI → mm
                x0 = min(p[0] for p in bbox) * scale
                y0 = min(p[1] for p in bbox) * scale
                x1 = max(p[0] for p in bbox) * scale
                y1 = max(p[1] for p in bbox) * scale

                blocks.append(TextBlock(
                    text=text.strip(),
                    bbox=(x0, y0, x1, y1),
                    font_name="OCR",
                    font_size=10.5,
                    page_number=page_index + 1,
                ))

        return ParsedPage(
            blocks=blocks,
            page_number=page_index + 1,
            width_mm=width_mm,
            height_mm=height_mm,
        )
