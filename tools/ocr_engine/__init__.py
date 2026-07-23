"""Shared OCR engine module.

Provides a unified interface over PaddleOCR 3.x so both
``pdf_converter`` and ``ocr_recognizer`` use the same backend.
"""

from tools.ocr_engine.base import BaseRecognizer, OCRRegion
from tools.ocr_engine.paddle_recognizer import PaddleRecognizer

__all__ = ["BaseRecognizer", "OCRRegion", "PaddleRecognizer"]
