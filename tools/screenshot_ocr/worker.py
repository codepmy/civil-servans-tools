"""截图 OCR 后台线程 — 识别文字（不操作剪贴板）。

参考 ``tools/ocr_recognizer/ui/worker.py`` 的 QThread 模式。

剪贴板写入由主线程在收到 ``succeeded`` 信号后执行。
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal


class ScreenshotOCRWorker(QThread):
    """对截图 numpy 数组执行 OCR。

    **不** 直接操作剪贴板（COM 线程安全限制），而是将
    识别文本通过 ``succeeded`` 信号发回主线程处理。

    Emits:
        progress: ``(percent: int, stage: str)``
        succeeded: ``(text: str)`` — 识别出的纯文本
        failed: ``(message: str)``
    """

    progress  = pyqtSignal(int, str)
    succeeded = pyqtSignal(str)
    failed    = pyqtSignal(str)

    def __init__(
        self,
        image: np.ndarray,
        engine=None,  # PaddleRecognizer | None — 外部传入单例
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._image = image
        self._engine = engine

    # ── Thread entry point ──────────────────────────────────────────

    def run(self) -> None:
        try:
            self.progress.emit(5, "初始化 OCR 引擎…")

            engine = self._engine
            if engine is None:
                from tools.ocr_engine.paddle_recognizer import PaddleRecognizer
                engine = PaddleRecognizer(handwritten=False)
                engine.warm_up()

            self.progress.emit(40, "正在识别文字…")
            regions = engine.recognize(self._image)

            if not regions:
                self.succeeded.emit("")
                self.progress.emit(100, "完成 — 未检测到文字")
                return

            self.progress.emit(70, "组装文本…")
            text = _regions_to_text(regions)

            self.progress.emit(100, "完成")
            self.succeeded.emit(text)

        except Exception as exc:
            self.failed.emit(str(exc))


# ═══════════════════════════════════════════════════════════════════════
# 文本组装（复用 OCR 识别工具的逻辑）
# ═══════════════════════════════════════════════════════════════════════

def _regions_to_text(regions) -> str:
    """将 OCRRegion 列表按阅读顺序组装为纯文本。

    按从上到下、从左到右排列，行间距较大时插入空行。
    """
    sorted_regions = sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0]))

    heights = [
        r.bbox[3] - r.bbox[1]
        for r in sorted_regions
        if (r.bbox[3] - r.bbox[1]) > 0
    ]
    median_h = sorted(heights)[len(heights) // 2] if heights else 20

    lines: list[str] = []
    prev_y1 = float("-inf")

    for region in sorted_regions:
        y0 = region.bbox[1]
        gap = y0 - prev_y1 if prev_y1 > float("-inf") else 0
        if gap > median_h * 1.5 and lines:
            lines.append("")
        lines.append(region.text)
        prev_y1 = region.bbox[3]

    return "\n".join(lines)
