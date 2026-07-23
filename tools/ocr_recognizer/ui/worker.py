"""Background OCR worker thread.

Runs the full OCR pipeline (load → preprocess → recognise → annotate)
on a QThread so the UI stays responsive.
"""

from __future__ import annotations

from PIL import Image
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

from tools.ocr_engine import OCRRegion, PaddleRecognizer
from tools.ocr_recognizer.core.preprocessing import preprocess_for_ocr


class OCRWorker(QThread):
    """Recognise text in a single image file.

    Emits:
        progress: ``(percent: int, stage: str)`` — stage update.
        succeeded: ``(regions: list[OCRRegion], annotated: np.ndarray | None)``
        failed: ``(message: str)``
    """

    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(list, object)  # list[OCRRegion], np.ndarray | None
    failed = pyqtSignal(str)

    def __init__(
        self,
        image_path: str,
        handwritten: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._image_path = image_path
        self._handwritten = handwritten

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self.progress.emit(10, "加载图片…")

            img = Image.open(self._image_path)
            # Normalise to RGB upfront
            img = img.convert("RGB")
            img_array = np.array(img)

            self.progress.emit(20, "预处理…")
            processed = preprocess_for_ocr(
                img_array, handwritten=self._handwritten
            )

            self.progress.emit(30, "初始化 OCR 引擎…")
            engine = PaddleRecognizer(handwritten=self._handwritten)

            if PaddleRecognizer.is_first_time():
                self.progress.emit(
                    40, "首次使用，正在下载模型（约 100 MB）…"
                )

            engine.warm_up()

            self.progress.emit(50, "正在识别文字…")
            regions = engine.recognize(processed)

            self.progress.emit(90, "生成标注…")
            annotated = (
                _draw_annotations(img_array, regions)
                if regions
                else None
            )

            self.progress.emit(100, "完成！")
            self.succeeded.emit(regions, annotated)

        except Exception as exc:
            self.failed.emit(str(exc))


# ------------------------------------------------------------------
# Annotation helpers
# ------------------------------------------------------------------

def _draw_annotations(
    image: np.ndarray, regions: list[OCRRegion]
) -> np.ndarray:
    """Return a copy of *image* with confidence-coloured bounding boxes."""
    from PIL import ImageDraw

    pil = Image.fromarray(image)
    draw = ImageDraw.Draw(pil)

    for region in regions:
        color = _confidence_color(region.confidence)
        x0, y0, x1, y1 = region.bbox
        draw.rectangle([x0, y0, x1, y1], outline=color, width=2)

    return np.array(pil)


_CONFIDENCE_COLORS: tuple[tuple[int, int, int, int], ...] = (
    (220, 38, 38),     # red    < 0.5
    (234, 179, 8),     # amber  0.5-0.7
    (250, 204, 21),    # yellow 0.7-0.9
    (34, 197, 94),     # green  >= 0.9
)
_CONFIDENCE_THRESHOLDS: tuple[float, ...] = (0.5, 0.7, 0.9)


def _confidence_color(conf: float) -> tuple[int, int, int]:
    for threshold, color in zip(
        _CONFIDENCE_THRESHOLDS, _CONFIDENCE_COLORS
    ):
        if conf < threshold:
            return color
    return _CONFIDENCE_COLORS[-1]
