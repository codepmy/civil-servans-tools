"""Image preprocessing for OCR recognition.

Uses Pillow only (no opencv-python dependency) to keep the
installation footprint small. The pipeline is configurable:
printed text gets minimal processing, handwritten text gets
contrast enhancement, sharpening, and denoising.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


def preprocess_for_ocr(
    image: np.ndarray, *, handwritten: bool = False
) -> np.ndarray:
    """Prepare an image array for OCR.

    Args:
        image: Source image as a numpy array (uint8, any channel layout).
        handwritten: When ``True``, apply a more aggressive preprocessing
            pipeline suited for handwriting.

    Returns:
        RGB numpy array ready to pass to ``PaddleRecognizer.recognize()``.
    """
    pil_img = Image.fromarray(image.astype(np.uint8))

    if handwritten:
        pil_img = _handwritten_preprocess(pil_img)

    return np.array(pil_img.convert("RGB"))


def _handwritten_preprocess(img: Image.Image) -> Image.Image:
    """Enhance contrast, sharpen, and denoise for handwriting."""
    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    return img
