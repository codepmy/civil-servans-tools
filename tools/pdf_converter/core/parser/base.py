"""PDF解析器抽象基类。"""

from abc import ABC, abstractmethod
from typing import Callable

from tools.pdf_converter.core.models import ParsedDocument


class BaseParser(ABC):
    """PDF解析器抽象基类。"""

    @abstractmethod
    def parse(self, path: str, progress: Callable[[int, str], None] = None) -> ParsedDocument:
        """解析PDF文件为结构化文档模型。

        Args:
            path: PDF文件路径
            progress: 进度回调 (percent, stage_name)

        Returns:
            ParsedDocument 结构化文档
        """
        ...

    @abstractmethod
    def can_handle(self, path: str) -> bool:
        """判断此解析器能否处理给定PDF。

        Args:
            path: PDF文件路径

        Returns:
            True 如果可以处理
        """
        ...
