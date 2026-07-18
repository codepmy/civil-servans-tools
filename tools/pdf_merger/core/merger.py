"""PDF拼合核心逻辑：使用PyMuPDF将多个PDF按顺序合并为一个。"""

import io
from pathlib import Path
from typing import Callable

import fitz


class PdfMerger:
    """将多个PDF文件按指定顺序合并为一个PDF。"""

    def merge(
        self,
        paths: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
        page_ranges: list[tuple[int, int]] | None = None,
    ) -> bytes:
        """按 *paths* 顺序合并PDF，返回合并后的 PDF bytes。

        Args:
            paths: 按合并顺序排列的 PDF 文件路径列表。
            progress_callback: 可选进度回调，签名 (current, total, filename)。
            page_ranges: 可选页码范围列表，每个元素为 (start, end)（从 1 开始）。
                         为 None 时合并全部页面。

        Returns:
            合并后的 PDF 文件字节数据。

        Raises:
            FileNotFoundError: 路径不存在时抛出。
            ValueError: 路径列表为空时抛出。
            RuntimeError: 合并过程中发生错误时抛出。
        """
        if not paths:
            raise ValueError("文件列表为空，请至少添加一个PDF文件。")

        total = len(paths)
        merged = fitz.open()

        try:
            for idx, path in enumerate(paths):
                file_path = Path(path)
                if not file_path.exists():
                    raise FileNotFoundError(f"文件不存在：{path}")

                filename = file_path.name
                if progress_callback:
                    progress_callback(idx + 1, total, filename)

                try:
                    src = fitz.open(str(file_path))
                except Exception as exc:
                    raise RuntimeError(f"无法打开PDF文件：{filename}\n{exc}") from exc

                try:
                    if page_ranges and idx < len(page_ranges):
                        start, end = page_ranges[idx]
                        # 从 1-indexed 转为 0-indexed，并钳制范围
                        start_0 = max(0, start - 1)
                        end_0 = min(src.page_count - 1, end - 1)
                        if start_0 <= end_0:
                            merged.insert_pdf(src, from_page=start_0, to_page=end_0)
                    else:
                        merged.insert_pdf(src)
                except Exception as exc:
                    raise RuntimeError(
                        f"合并文件时出错：{filename}\n{exc}"
                    ) from exc
                finally:
                    src.close()

            buffer = io.BytesIO()
            merged.save(buffer)
            return buffer.getvalue()

        finally:
            merged.close()
