from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from tools.pdf_converter.core.generator.font_manager import FontManager


DEFAULT_GRID_LINE_WIDTH = 0.30
DEFAULT_GRID_LINE_COLOR = "#FF0000"


@dataclass(frozen=True)
class AnswerSheetQuestion:
    """分题模式中的一道题。"""

    title: str
    word_count: int


@dataclass(frozen=True)
class AnswerSheetConfig:
    """答题纸生成配置。"""

    mode: str = "standard"
    page_count: int = 1
    questions: tuple[AnswerSheetQuestion, ...] = ()
    title: str = "申论答题纸"
    font_name: str = "SimSun"
    grid_line_width: float = DEFAULT_GRID_LINE_WIDTH
    grid_line_color: str = DEFAULT_GRID_LINE_COLOR


@dataclass(frozen=True)
class AnswerSheetLine:
    """答题纸中的一行格子。"""

    cell_count: int
    markers: tuple[str, ...] = ()
    gap_before_mm: float = 0.0
    question_title: str = ""


@dataclass(frozen=True)
class AnswerSheetPage:
    """待绘制的一页答题纸。"""

    lines: tuple[AnswerSheetLine, ...]
    page_number: int
    total_pages: int

    @property
    def cell_count(self) -> int:
        return sum(line.cell_count for line in self.lines)


class AnswerSheetGenerator:
    """生成申论答题纸，并支持 PDF 与 PNG 导出。"""

    COLS = 25
    ROWS = 24
    CELLS_PER_PAGE = COLS * ROWS

    PAGE_WIDTH_MM = 210.0
    PAGE_HEIGHT_MM = 297.0
    CELL_WIDTH_MM = 7.5
    CELL_HEIGHT_MM = 8.6
    ROW_GAP_MM = 3.1
    QUESTION_GAP_MM = 1.2
    GRID_LEFT_MM = 8.0
    GRID_TOP_MM = 5.0
    GRID_BOTTOM_MM = 5.0
    LINE_COLOR = colors.HexColor(DEFAULT_GRID_LINE_COLOR).rgb()
    MARK_COLOR = (0.28, 0.28, 0.28)

    def __init__(self, font_manager: FontManager | None = None):
        self._font_manager = font_manager or FontManager()
        try:
            self._font_manager.register_all()
        except Exception:
            pass

    def build_pages(self, config: AnswerSheetConfig) -> list[AnswerSheetPage]:
        """根据模式生成页面描述。"""
        if config.mode == "questions":
            return self._build_question_pages(config.questions)

        page_count = max(1, int(config.page_count))
        pages = [
            AnswerSheetPage(
                lines=self._standard_page_lines(),
                page_number=i,
                total_pages=page_count,
            )
            for i in range(1, page_count + 1)
        ]
        return pages

    def generate_pdf(self, config: AnswerSheetConfig) -> bytes:
        """生成 PDF bytes。"""
        pages = self.build_pages(config)
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        font_name = self._resolve_font(config.font_name)
        c.setTitle("申论答题纸")

        for page in pages:
            self._draw_page(c, page, font_name, config)
            c.showPage()

        c.save()
        return buffer.getvalue()

    def export_pngs(
        self,
        pdf_bytes: bytes,
        output_dir: str | Path,
        base_name: str = "shenlun_answer_sheet",
        dpi: int = 220,
    ) -> list[Path]:
        """将 PDF 每页渲染为 PNG 图片。"""
        import fitz

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for index, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                path = out_dir / f"{base_name}_{index:02d}.png"
                pix.save(str(path))
                paths.append(path)
        finally:
            doc.close()
        return paths

    def _build_question_pages(self, questions: tuple[AnswerSheetQuestion, ...]) -> list[AnswerSheetPage]:
        raw_pages: list[list[AnswerSheetLine]] = [[]]
        rows_used = 0
        height_used_mm = 0.0
        max_height_mm = self.PAGE_HEIGHT_MM - self.GRID_TOP_MM - self.GRID_BOTTOM_MM

        for q_index, question in enumerate(questions, start=1):
            words = max(1, int(question.word_count))
            question_offset = 0
            first_line_for_question = True

            while question_offset < words:
                remaining = words - question_offset
                cells = min(self.COLS, remaining)
                start = question_offset + 1
                end = question_offset + cells
                markers = tuple(
                    f"({mark}字)"
                    for mark in range(100, end + 1, 100)
                    if start <= mark <= end
                )
                gap = (
                    self.QUESTION_GAP_MM
                    if q_index > 1 and first_line_for_question and rows_used > 0
                    else 0.0
                )
                if rows_used >= self.ROWS or height_used_mm + gap + self.CELL_HEIGHT_MM > max_height_mm:
                    raw_pages.append([])
                    rows_used = 0
                    height_used_mm = 0.0
                    gap = 0.0

                raw_pages[-1].append(
                    AnswerSheetLine(
                        cell_count=cells,
                        markers=markers,
                        gap_before_mm=gap,
                        question_title=question.title.strip() if first_line_for_question else "",
                    )
                )
                question_offset += cells
                rows_used += 1
                first_line_for_question = False

        if not raw_pages[-1]:
            raw_pages.pop()
        total_pages = max(1, len(raw_pages))
        return [
            AnswerSheetPage(
                lines=tuple(lines),
                page_number=index,
                total_pages=total_pages,
            )
            for index, lines in enumerate(raw_pages, start=1)
        ]

    def _standard_page_lines(self) -> tuple[AnswerSheetLine, ...]:
        lines: list[AnswerSheetLine] = []
        for row in range(1, self.ROWS + 1):
            word_no = row * self.COLS
            marker = (f"({word_no}字)",) if word_no % 100 == 0 else ()
            lines.append(AnswerSheetLine(cell_count=self.COLS, markers=marker))
        return tuple(lines)

    def _draw_page(self, c: canvas.Canvas, page: AnswerSheetPage, font_name: str, config: AnswerSheetConfig):
        y_top = (self.PAGE_HEIGHT_MM - self.GRID_TOP_MM) * mm
        current_offset_mm = 0.0

        grid_line_width = max(0.1, min(float(config.grid_line_width), 2.0))
        grid_line_color = self._parse_grid_line_color(config.grid_line_color)
        c.setLineWidth(grid_line_width)
        c.setStrokeColorRGB(*grid_line_color)
        c.setFillColorRGB(*self.MARK_COLOR)
        c.setFont(font_name, 5.2)

        for line in page.lines:
            if line.gap_before_mm:
                current_offset_mm += line.gap_before_mm
            row_top = y_top - current_offset_mm * mm
            self._draw_line(c, line, row_top, font_name, grid_line_color, grid_line_width)
            current_offset_mm += self.CELL_HEIGHT_MM + self.ROW_GAP_MM - line.gap_before_mm

    def _draw_line(
        self,
        c: canvas.Canvas,
        line: AnswerSheetLine,
        row_top: float,
        font_name: str,
        grid_line_color: tuple[float, float, float],
        grid_line_width: float,
    ):
        left = self.GRID_LEFT_MM * mm
        cell_w = self.CELL_WIDTH_MM * mm
        cell_h = self.CELL_HEIGHT_MM * mm
        row_bottom = row_top - cell_h
        cells = max(1, min(line.cell_count, self.COLS))

        if line.question_title:
            self._draw_question_title(c, line.question_title, row_bottom, font_name)

        c.setStrokeColorRGB(*grid_line_color)
        c.setLineWidth(grid_line_width)
        for col in range(cells):
            x = left + col * cell_w
            c.rect(x, row_bottom, cell_w, cell_h, stroke=1, fill=0)

        if not line.markers:
            return

        c.setFillColorRGB(*self.MARK_COLOR)
        c.setFont(font_name, 5.2)
        grid_right = left + self.COLS * cell_w
        for marker in line.markers:
            label_width = pdfmetrics.stringWidth(marker, font_name, 5.2)
            x = grid_right - label_width - 0.6 * mm
            y = row_bottom - 1.9 * mm
            c.drawString(x, y, marker)

    def _draw_question_title(self, c: canvas.Canvas, title: str, row_bottom: float, font_name: str):
        max_width = max(1.0, self.GRID_LEFT_MM - 1.7) * mm
        font_size = 6.2
        label = title
        while pdfmetrics.stringWidth(label, font_name, font_size) > max_width and font_size > 4.5:
            font_size -= 0.2
        while pdfmetrics.stringWidth(label, font_name, font_size) > max_width and len(label) > 2:
            label = label[:-2] + "..."

        c.saveState()
        c.setFillColorRGB(*self.MARK_COLOR)
        c.setFont(font_name, font_size)
        label_width = pdfmetrics.stringWidth(label, font_name, font_size)
        x = max(0.8, self.GRID_LEFT_MM - 0.8) * mm - label_width
        y = row_bottom + self.CELL_HEIGHT_MM * 0.42 * mm
        c.drawString(x, y, label)
        c.restoreState()

    def _resolve_font(self, preferred: str) -> str:
        try:
            return self._font_manager.get_fallback(preferred or "SimSun")
        except Exception:
            return "Helvetica"

    def _parse_grid_line_color(self, color_value: str) -> tuple[float, float, float]:
        try:
            return colors.HexColor(color_value or DEFAULT_GRID_LINE_COLOR).rgb()
        except Exception:
            return self.LINE_COLOR
