"""OCR parser for scanned/image PDFs using PaddleOCR.

PaddleOCR runs on PaddlePaddle. If a CUDA-enabled PaddlePaddle build is
installed, OCR will use the NVIDIA GPU automatically; otherwise it falls
back to CPU mode.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import fitz
import numpy as np

from tools.ocr_engine import PaddleRecognizer, OCRRegion
from tools.pdf_converter.core.models import ParsedDocument, ParsedPage, TextBlock
from tools.pdf_converter.core.parser.base import BaseParser


class OCRParser(BaseParser):
    """PaddleOCR-based parser for scanned/image PDFs."""

    def __init__(self) -> None:
        self._ocr: PaddleRecognizer | None = None
        self._device_label = "CPU"
        self._using_gpu = False

    @classmethod
    def is_first_time(cls) -> bool:
        """Return whether the PaddleOCR model cache appears empty."""
        return PaddleRecognizer.is_first_time()

    @property
    def device_label(self) -> str:
        return self._device_label

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu

    @staticmethod
    def _ensure_ocr_engine() -> PaddleRecognizer:
        """Create a PaddleRecognizer, raising a user-friendly error on failure."""
        try:
            return PaddleRecognizer()
        except ImportError as exc:
            raise RuntimeError(
                "当前环境未安装 OCR 依赖（PaddleOCR/PaddlePaddle），"
                "请运行 setup.bat 安装。\n"
                "如果需要 GPU 加速，请确认 setup.bat 末尾的 CUDA 检查通过。\n"
                "\n"
                f"原始错误: {exc}"
            ) from exc

    def _get_ocr(self) -> PaddleRecognizer:
        """Lazily load PaddleOCR and warm it up."""
        if self._ocr is not None:
            return self._ocr

        self._ocr = self._ensure_ocr_engine()
        self._ocr.warm_up()

        self._using_gpu = self._ocr.using_gpu
        self._device_label = self._ocr.device_label
        return self._ocr

    # ------------------------------------------------------------------
    # BaseParser interface
    # ------------------------------------------------------------------

    def can_handle(self, path: str) -> bool:
        return True

    def parse(
        self, path: str, progress: Callable[[int, str], None] = None
    ) -> ParsedDocument:
        doc = fitz.open(path)
        total = doc.page_count
        pages: list[ParsedPage] = []

        try:
            ocr = self._get_ocr()
            mode = "GPU OCR" if self._using_gpu else "CPU OCR"
            if progress:
                progress(5, f"{mode} 已启动（{self._device_label}）")

            for i in range(total):
                if progress:
                    progress(
                        int((i + 1) / total * 100),
                        f"{mode} ... {i + 1}/{total}",
                    )

                page = doc[i]
                parsed_page = self._ocr_page(page, i, ocr)
                pages.append(parsed_page)
        finally:
            doc.close()

        return ParsedDocument(
            pages=pages,
            metadata={
                "title": "",
                "page_count": total,
                "file_path": "",
                "ocr_device": self._device_label,
                "ocr_gpu": self._using_gpu,
            },
            source_type="image",
        )

    # ------------------------------------------------------------------
    # Page-level OCR
    # ------------------------------------------------------------------

    def _ocr_page(
        self, page: fitz.Page, page_index: int, ocr: PaddleRecognizer
    ) -> ParsedPage:
        page_rect = page.rect
        width_mm = page_rect.width * 25.4 / 72
        height_mm = page_rect.height * 25.4 / 72

        dpi = 200
        pix = page.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        if img.shape[2] == 4:
            img = img[:, :, :3]

        regions = ocr.recognize(img)

        blocks: list[TextBlock] = []
        scale = 25.4 / dpi  # pixels → mm
        for region in regions:
            if not self._should_keep_ocr_text(region.text, region.confidence):
                continue

            x0 = region.bbox[0] * scale
            y0 = region.bbox[1] * scale
            x1 = region.bbox[2] * scale
            y1 = region.bbox[3] * scale

            stripped = region.text.strip()
            if stripped:
                blocks.append(
                    TextBlock(
                        text=stripped,
                        bbox=(x0, y0, x1, y1),
                        font_name="OCR",
                        font_size=10.5,
                        page_number=page_index + 1,
                    )
                )

        return ParsedPage(
            blocks=blocks,
            page_number=page_index + 1,
            width_mm=width_mm,
            height_mm=height_mm,
        )

    # ------------------------------------------------------------------
    # Quality filter
    # ------------------------------------------------------------------

    @staticmethod
    def _should_keep_ocr_text(text: str, confidence: float) -> bool:
        stripped = (text or "").strip()
        if not stripped:
            return False
        if confidence >= 0.5:
            return True
        if confidence < 0.35:
            return False
        compact = re.sub(r"\s+", "", stripped)
        return bool(
            re.fullmatch(r"\d{1,3}[\.．。、]?", compact)
            or re.fullmatch(
                r"[A-D][\.．。_\-—一\)）]?", compact
            )
        )
