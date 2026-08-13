"""手动双面打印页序重排核心逻辑：将PDF拆分为正反面两份打印文件。

原理：单面打印机通过两次打印实现双面——
    第一次打印所有奇数页（正面），把纸张翻面放回进纸盒，
    第二次打印所有偶数页（反面），每张纸两面都有内容。

偶数页顺序取决于打印机出纸方式：
    - 出纸面朝下（多数激光打印机）：纸叠顶部是最后打印的页，
      翻面后打印机先取顶部的纸，需从最后一个偶数页往前打印（逆序）。
    - 出纸面朝上（多数喷墨打印机）：纸叠倒头放入后顺序反转，
      偶数页保持原顺序打印即可。
"""

import io
from pathlib import Path

import fitz


class DuplexReorderer:
    """将PDF重排为手动双面打印所需的正/反面两份文件。"""

    def reorder(
        self,
        path: str,
        face_down: bool = True,
        flip_short_edge: bool = False,
    ) -> tuple[bytes, bytes]:
        """按手动双面打印需求重排页面，返回 (正面bytes, 反面bytes)。

        Args:
            path: 源 PDF 文件路径。
            face_down: True 表示打印机出纸时印好的一面朝下（多数激光打印机），
                       偶数页逆序排列；False 表示面朝上（多数喷墨打印机），
                       偶数页保持原顺序。
            flip_short_edge: True 表示翻面方式为上下翻（短边为轴），
                             反面每页旋转 180°；False 为左右翻（长边为轴），不旋转。

        Returns:
            (正面 PDF bytes, 反面 PDF bytes)。正面为奇数页按原顺序，
            反面为偶数页按出纸方式排列。页数为 1 时反面为 b""（空批）。

        Raises:
            FileNotFoundError: 路径不存在时抛出。
            ValueError: PDF 页数为 0 时抛出。
            RuntimeError: 打开或重排过程中发生错误时抛出。
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在：{path}")

        try:
            src = fitz.open(str(file_path))
        except Exception as exc:
            raise RuntimeError(f"无法打开PDF文件：{file_path.name}\n{exc}") from exc

        try:
            n = src.page_count
            if n == 0:
                raise ValueError("PDF 文件没有页面。")

            front = list(range(0, n, 2))  # 奇数页 0-based：[0, 2, 4, ...]
            back = list(range(1, n, 2))   # 偶数页 0-based：[1, 3, 5, ...]
            if face_down:
                back.reverse()

            front_bytes = self._build(src, front, rotate=False)
            back_bytes = self._build(src, back, rotate=flip_short_edge)
            return front_bytes, back_bytes
        finally:
            src.close()

    def _build(self, src: fitz.Document, pages: list[int], rotate: bool) -> bytes:
        """按给定页序抽取页面生成新PDF，返回 bytes。

        空批（pages 为空）返回 b""——PyMuPDF 无法保存 0 页 PDF，
        由 UI 层决定是否跳过对应文件的生成。
        """
        if not pages:
            return b""
        out = fitz.open()
        try:
            for p in pages:
                out.insert_pdf(src, from_page=p, to_page=p)
                if rotate:
                    # 只旋转输出文档刚插入的页，不污染源文档
                    page = out[out.page_count - 1]
                    page.set_rotation((page.rotation + 180) % 360)
            buffer = io.BytesIO()
            out.save(buffer)
            return buffer.getvalue()
        finally:
            out.close()
