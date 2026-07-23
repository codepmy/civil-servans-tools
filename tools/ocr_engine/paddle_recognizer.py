"""PaddleOCR 2.x recognizer implementation.

Wraps PaddleOCR behind the :class:`BaseRecognizer` interface so
callers never touch the PaddleOCR API directly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

# Must be set BEFORE any `import paddle` — PaddlePaddle reads these
# environment variables at import time and caches the values.
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from tools.ocr_engine.base import BaseRecognizer, OCRRegion


class PaddleRecognizer(BaseRecognizer):
    """OCR engine backed by PaddleOCR 2.x + PaddlePaddle 2.x.

    PaddleOCR 2.x is used (not 3.x) because 3.x's PIR executor has a
    known OneDNN incompatibility on Windows that prevents GPU usage.
    2.x is stable and GPU works out-of-the-box.

    Parameters:
        handwritten:
            When ``True`` the engine lowers detection thresholds to
            capture more candidate regions – useful for handwriting.
    """

    _MODEL_DIR = Path.home() / ".paddleocr"

    # ------------------------------------------------------------------
    # Construction & device probing
    # ------------------------------------------------------------------

    def __init__(self, handwritten: bool = False) -> None:
        self._handwritten = bool(handwritten)
        self._ocr: Any = None
        self._using_gpu, self._device_label = self._detect_gpu()

    # PaddlePaddle 2.6.2 supports up to CC 8.9 (Ada Lovelace).
    # Blackwell (CC 12.0 / RTX 50 series) is unsupported.
    _MAX_SUPPORTED_CC = (9, 0)

    @staticmethod
    def _detect_gpu() -> tuple[bool, str]:
        """Probe PaddlePaddle for CUDA support.

        Returns (False, reason) when a GPU is present but unsupported
        (e.g. RTX 50 series on PaddlePaddle 2.6.2).
        """
        try:
            import paddle  # type: ignore[import-untyped]
        except ImportError:
            return False, "CPU"

        try:
            if paddle.is_compiled_with_cuda():
                if paddle.device.cuda.device_count() > 0:
                    props = paddle.device.cuda.get_device_properties(0)
                    name = props.name
                    cc = (props.major, props.minor)
                    if cc > PaddleRecognizer._MAX_SUPPORTED_CC:
                        return (
                            False,
                            f"CPU（{name} 计算能力 {cc[0]}.{cc[1]} "
                            "不被 PaddlePaddle 2.6.2 支持，"
                            "请等待后续版本适配 RTX 50 系列）",
                        )
                    return True, f"GPU: {name}"
        except Exception:
            pass

        return False, "CPU"

    @staticmethod
    def _verify_cuda_runtime() -> None:
        """Verify cuDNN/CUDA runtime is actually usable.

        Raises RuntimeError with install instructions if cuDNN or
        other CUDA runtime libs are missing.
        """
        try:
            import paddle  # type: ignore[import-untyped]
        except ImportError:
            return  # CPU-only, nothing to verify

        try:
            # Try a tiny GPU op — this will fail if cuDNN/cuBLAS/cuFFT
            # DLLs are missing even though CUDA driver is present.
            paddle.device.set_device("gpu")
            x = paddle.to_tensor([1.0])
            _ = x + 1.0
        except Exception as exc:
            msg = str(exc)
            if "cudnn" in msg.lower() or "third-party dynamic library" in msg.lower():
                raise RuntimeError(
                    "CUDNN_MISSING\n"
                    "检测到 NVIDIA GPU，但 cuDNN 8.x 运行时库未安装。\n\n"
                    "GPU 加速需要 cuDNN 8.x（与 CUDA 11.x 配套）。\n"
                    "请从 NVIDIA cuDNN Archive 下载：\n"
                    "https://developer.nvidia.com/rdp/cudnn-archive\n\n"
                    "安装步骤：\n"
                    "1. 下载 cuDNN v8.9.x for CUDA 11.x (Windows x64)\n"
                    "2. 解压后将 bin/ 目录加入系统 PATH 环境变量\n"
                    "3. 重启本程序\n\n"
                    f"原始错误: {exc}"
                ) from exc
            raise

    # ------------------------------------------------------------------
    # BaseRecognizer properties
    # ------------------------------------------------------------------

    @property
    def device_label(self) -> str:
        return self._device_label

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu

    @classmethod
    def is_first_time(cls) -> bool:
        """Model cache is empty → PaddleOCR will download on first use."""
        return (
            not cls._MODEL_DIR.exists()
            or not any(cls._MODEL_DIR.iterdir())
        )

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        """Return ``(True, "")`` if PaddleOCR can be imported, or
        ``(False, reason)`` with a user-facing message."""
        try:
            import paddle  # noqa: F401
            from paddleocr import PaddleOCR  # noqa: F401
        except ImportError as exc:
            return (
                False,
                "当前环境未安装 OCR 依赖（PaddleOCR/PaddlePaddle）。\n\n"
                "请运行项目根目录下的 setup.bat 完成安装，\n"
                "安装完成后重新启动本程序即可使用 OCR 功能。\n\n"
                f"原始错误: {exc}",
            )
        return True, ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def warm_up(self) -> None:
        """Pre-load (and potentially download) models."""
        self._get_ocr()

    def recognize(self, image: np.ndarray) -> list[OCRRegion]:
        """Run OCR on a single image array.

        *image* must be uint8.  The method normalises grayscale, RGBA,
        and other channel counts to RGB internally.
        """
        ocr = self._get_ocr()
        rgb = _ensure_rgb(image)

        result = ocr.ocr(rgb)
        if not result or not result[0]:
            return []

        return [_detection_to_region(det) for det in result[0]]

    def recognize_batch(
        self, images: list[np.ndarray]
    ) -> list[list[OCRRegion]]:
        return [self.recognize(img) for img in images]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_ocr(self) -> Any:
        """Lazily initialise and return the PaddleOCR instance.

        The first call may download models (∼100 MB) if this is the
        first-ever run.
        """
        if self._ocr is not None:
            return self._ocr

        # ── verify GPU runtime before creating PaddleOCR ──────────
        if self._using_gpu:
            self._verify_cuda_runtime()

        try:
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "当前环境未安装 OCR 依赖（PaddleOCR/PaddlePaddle），"
                "请运行 setup.bat 安装。\n"
                "如果需要 GPU 加速，请确认 setup.bat 末尾的 CUDA 检查通过。\n"
                "\n"
                f"原始错误: {exc}"
            ) from exc

        params: dict[str, Any] = {
            "lang": "ch",
            "use_gpu": self._using_gpu,
        }

        if self._handwritten:
            params.update({
                "det_db_thresh": 0.3,
                "det_db_box_thresh": 0.4,
                "drop_score": 0.3,
                "use_space_char": True,
            })

        self._ocr = PaddleOCR(**params)
        return self._ocr


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _ensure_rgb(image: np.ndarray) -> np.ndarray:
    """Return a uint8 RGB copy of *image* regardless of input channels."""
    if image.ndim == 2:
        return np.stack([image] * 3, axis=-1)
    if image.ndim == 3 and image.shape[2] == 4:
        return image[:, :, :3]
    if image.ndim == 3 and image.shape[2] == 3:
        return image
    from PIL import Image

    return np.array(Image.fromarray(image).convert("RGB"))


def _detection_to_region(detection: Any) -> OCRRegion:
    """Convert a single PaddleOCR 2.x detection to an :class:`OCRRegion`.

    A detection is ``[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], (text, conf)]``.
    The 4-point polygon bbox is collapsed to an axis-aligned rectangle.
    """
    bbox_points, (text, confidence) = detection
    xs = [p[0] for p in bbox_points]
    ys = [p[1] for p in bbox_points]
    return OCRRegion(
        text=text,
        bbox=(min(xs), min(ys), max(xs), max(ys)),
        confidence=float(confidence),
    )
