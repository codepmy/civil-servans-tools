"""Shared OCR engine module.

Provides a unified interface over PaddleOCR 3.x so both
``pdf_converter`` and ``ocr_recognizer`` use the same backend.
"""

from tools.ocr_engine.base import BaseRecognizer, OCRRegion

__all__ = ["BaseRecognizer", "OCRRegion"]

# PaddleRecognizer is NOT imported at module level to prevent PyInstaller
# from statically discovering and bundling the entire PaddlePaddle library
# (~1.8 GB).  Callers that need recognition must use a lazy import:
#     from tools.ocr_engine.paddle_recognizer import PaddleRecognizer
