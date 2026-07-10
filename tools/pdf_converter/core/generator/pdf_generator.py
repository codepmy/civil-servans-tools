"""PDF生成器: 使用ReportLab将排版后的文档渲染为PDF。"""

import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from tools.pdf_converter.core.models import LaidOutDocument, LaidOutPage, PageElement
from tools.pdf_converter.core.generator.font_manager import FontManager


class PDFGenerator:
    """将LaidOutDocument渲染为PDF。"""

    def __init__(self, font_manager: FontManager):
        self._font_manager = font_manager
        self._font_map: dict[str, str] = {}
        self._page_w_mm: float = 210
        self._page_h_mm: float = 297

    def generate(self, doc: LaidOutDocument) -> bytes:
        """生成PDF。"""
        self._build_font_map(doc)

        # 从config_snapshot获取纸张尺寸
        snap = doc.config_snapshot
        self._page_w_mm = snap.get("page_width_mm", 210)
        self._page_h_mm = snap.get("page_height_mm", 297)
        pagesize = (self._page_w_mm * mm, self._page_h_mm * mm)

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=pagesize)

        for page in doc.pages:
            self._draw_page(c, page)

        c.save()
        return buf.getvalue()

    def _build_font_map(self, doc: LaidOutDocument):
        """构建字体映射表(逻辑名→实际名)。"""
        all_fonts = set()
        for page in doc.pages:
            for elem in page.elements:
                all_fonts.add(elem.font_name)

        for font_name in all_fonts:
            self._font_map[font_name] = self._font_manager.get_fallback(font_name)

    def _resolve_font(self, name: str) -> str:
        """将逻辑字体名解析为实际可用字体名。"""
        if name in self._font_map:
            return self._font_map[name]
        return self._font_manager.get_fallback(name)

    def _draw_page(self, c: canvas.Canvas, page: LaidOutPage):
        """绘制一页。"""
        for elem in page.elements:
            self._draw_element(c, elem)

        # 页码已在PageElement中，draw完后结束页面
        c.showPage()

    def _draw_element(self, c: canvas.Canvas, elem: PageElement):
        """绘制单个页面元素。"""
        # 坐标转换
        x = elem.x_mm * mm
        y = (self._page_h_mm - elem.y_mm) * mm

        # 图片元素
        if elem.type == "image" and elem.image_data:
            self._draw_image(c, elem, x, y)
            return

        font_name = self._resolve_font(elem.font_name)
        try:
            c.setFont(font_name, elem.font_size)
        except Exception:
            fallback = self._font_manager.get_fallback("SimSun")
            c.setFont(fallback, elem.font_size)

        if elem.type == "page_number":
            text_width = c.stringWidth(elem.text, font_name, elem.font_size)
            x = (self._page_w_mm * mm - text_width) / 2
            c.drawString(x, y, elem.text)
            return

        if elem.type == "answer_line":
            c.drawString(x, y, elem.text)
            line_width = elem.width_mm * mm if elem.width_mm else 40 * mm
            c.line(x, y - 1 * mm, x + line_width, y - 1 * mm)
            return

        # 标准文本绘制
        c.drawString(x, y, elem.text)

    def _draw_image(self, c: canvas.Canvas, elem: PageElement, x: float, y: float):
        """在画布上绘制图片。"""
        import tempfile, os
        # ReportLab的drawImage需要文件路径或ImageReader
        # 将bytes写入临时文件
        try:
            from reportlab.lib.utils import ImageReader
            import io
            reader = ImageReader(io.BytesIO(elem.image_data))
            w = elem.image_w_mm * mm if elem.image_w_mm else 50 * mm
            h = elem.image_h_mm * mm if elem.image_h_mm else 50 * mm
            # y坐标: 图片左上角对齐
            c.drawImage(reader, x, y - h, width=w, height=h, preserveAspectRatio=True)
        except Exception as e:
            # 图片无法渲染时画一个占位框
            w = (elem.image_w_mm or 50) * mm
            h = (elem.image_h_mm or 30) * mm
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.setFillColorRGB(0.95, 0.95, 0.95)
            c.rect(x, y - h, w, h, fill=1, stroke=1)
            c.setFillColorRGB(0.3, 0.3, 0.3)
            c.setFont("Helvetica", 8)
            c.drawString(x + 5, y - h/2, "[图片]")
