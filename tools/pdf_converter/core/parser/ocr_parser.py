"""OCR parser for scanned/image PDFs using EasyOCR.

EasyOCR runs on PyTorch. If a CUDA-enabled PyTorch build is installed, OCR will
use the NVIDIA GPU automatically; otherwise it falls back to CPU mode.
"""

from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable

import fitz
import numpy as np

from tools.pdf_converter.core.models import ParsedDocument, ParsedPage, TextBlock
from tools.pdf_converter.core.parser.base import BaseParser


class OCRParser(BaseParser):
    """EasyOCR-based parser for scanned/image PDFs."""

    _MODEL_DIR = Path.home() / ".EasyOCR" / "model"

    def __init__(self):
        self._ocr = None
        self._device_label = "CPU"
        self._using_gpu = False

    @classmethod
    def is_first_time(cls) -> bool:
        """Return whether the EasyOCR model cache appears empty."""
        return not cls._MODEL_DIR.exists() or not any(cls._MODEL_DIR.iterdir())

    @property
    def device_label(self) -> str:
        return self._device_label

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu

    def _get_ocr(self):
        """Load EasyOCR lazily and prefer CUDA when it is truly available."""
        if self._ocr is not None:
            return self._ocr

        try:
            import easyocr
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "当前环境未安装 OCR 依赖（EasyOCR/PyTorch），请运行 setup.bat 安装。\n"
                "如果需要 GPU 加速，请确认 setup.bat 最后的 cuda available 为 True。\n\n"
                f"原始错误: {exc}"
            ) from exc

        if torch.cuda.is_available():
            try:
                device_name = torch.cuda.get_device_name(0)
                self._ocr = easyocr.Reader(["ch_sim", "en"], gpu=True, verbose=False)
                self._using_gpu = True
                self._device_label = f"GPU: {device_name}"
                return self._ocr
            except Exception as exc:
                self._log_gpu_fallback(exc, torch)
        elif self._has_nvidia_gpu():
            raise RuntimeError(
                "检测到 NVIDIA 显卡，但当前 PyTorch 不是可用的 CUDA 版本，OCR 不会使用 GPU。\n"
                "请重新运行 setup.bat；如果仍失败，请安装 Python 3.12 x64 后再运行 setup.bat。\n\n"
                f"torch={getattr(torch, '__version__', 'unknown')}, "
                f"cuda_build={torch.version.cuda}, cuda_available={torch.cuda.is_available()}"
            )

        self._ocr = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        self._using_gpu = False
        self._device_label = "CPU"
        return self._ocr

    @staticmethod
    def _has_nvidia_gpu() -> bool:
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return False
        try:
            result = subprocess.run(
                [nvidia_smi],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _log_gpu_fallback(exc: Exception, torch_module) -> None:
        import sys

        cuda_build = getattr(getattr(torch_module, "version", None), "cuda", None)
        print(
            "[OCR] GPU 初始化失败，已自动回退 CPU。"
            f" torch={getattr(torch_module, '__version__', 'unknown')},"
            f" cuda_build={cuda_build}, error={exc}",
            file=sys.stderr,
        )

    def can_handle(self, path: str) -> bool:
        return True

    def parse(
        self, path: str, progress: Callable[[int, str], None] = None
    ) -> ParsedDocument:
        doc = fitz.open(path)
        total = doc.page_count
        pages = []

        try:
            ocr = self._get_ocr()
            mode = "GPU OCR" if self._using_gpu else "CPU OCR"
            if progress:
                progress(5, f"{mode} 已启动（{self._device_label}）")

            for i in range(total):
                if progress:
                    progress(int((i + 1) / total * 100), f"{mode} ... {i + 1}/{total}")

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
                "file_path": "",  # Avoid cleaner re-reading image-only PDFs as text.
                "ocr_device": self._device_label,
                "ocr_gpu": self._using_gpu,
            },
            source_type="image",
        )

    def _ocr_page(self, page: fitz.Page, page_index: int, ocr) -> ParsedPage:
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

        results = ocr.readtext(img)

        blocks = []
        scale = 25.4 / dpi
        for bbox, text, confidence in results:
            if not self._should_keep_ocr_text(text, confidence):
                continue

            x0 = min(p[0] for p in bbox) * scale
            y0 = min(p[1] for p in bbox) * scale
            x1 = max(p[0] for p in bbox) * scale
            y1 = max(p[1] for p in bbox) * scale

            stripped = text.strip()
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
        return bool(re.fullmatch(r"\d{1,3}[\.\uff0e\u3002\u3001]?", compact) or re.fullmatch(r"[A-D][\.\uff0e\u3002_\-\u2014\u4e00\)\uff09]?", compact))
