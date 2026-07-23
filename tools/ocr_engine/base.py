"""OCR engine abstraction layer.

Defines the universal interface that all OCR recognizer implementations
must conform to. This keeps downstream code (pdf_converter, ocr_recognizer)
decoupled from any specific OCR library.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class OCRRegion:
    """A single recognized text region within an image.

    Attributes:
        text: Recognized text content.
        bbox: Axis-aligned bounding box as (x0, y0, x1, y1) in **pixel**
            coordinates relative to the input image. Origin is top-left.
        confidence: Recognition confidence in [0.0, 1.0].
    """

    text: str
    bbox: tuple[float, float, float, float]
    confidence: float


class BaseRecognizer(ABC):
    """Abstract interface for OCR engines.

    All OCR implementations used by the application must subclass this
    and implement every abstract method.
    """

    @abstractmethod
    def recognize(self, image: np.ndarray) -> list[OCRRegion]:
        """Run OCR on a single image.

        Args:
            image: RGB (H, W, 3), RGBA (H, W, 4), or grayscale (H, W)
                numpy array with dtype uint8.

        Returns:
            List of recognized text regions. May be empty if no text
            was detected.
        """
        ...

    @abstractmethod
    def recognize_batch(
        self, images: list[np.ndarray]
    ) -> list[list[OCRRegion]]:
        """Run OCR on multiple images (batch convenience).

        The default implementation calls ``recognize`` for each image
        sequentially. Engines may override this with true batching.
        """
        ...

    @property
    @abstractmethod
    def device_label(self) -> str:
        """Human-readable device identifier, e.g. ``"CPU"`` or
        ``"GPU: NVIDIA GeForce RTX 4060"``.
        """
        ...

    @property
    @abstractmethod
    def using_gpu(self) -> bool:
        """Whether the engine is currently using GPU acceleration."""
        ...

    @classmethod
    @abstractmethod
    def is_first_time(cls) -> bool:
        """Return ``True`` when the engine's model cache is empty.

        Used by the UI to show a first-time download progress message
        before the (potentially long) model download begins.
        """
        ...

    @abstractmethod
    def warm_up(self) -> None:
        """Pre-load models so the first ``recognize()`` call is fast.

        This should be called once after construction, typically from
        a background thread with progress reporting.
        """
        ...
