from __future__ import annotations

import json
import re
from typing import Callable

from app_paths import resource_path
from tools.pdf_converter.core.models import ParsedDocument, CleanedDocument, Question, Option

HEADER_CUTOFF_MM = 28.0
FOOTER_START_MM = 270.0
SECTION_MARKER = "__SECTION__"


def _u(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


DATA_ANALYSIS = _u(0x8D44, 0x6599, 0x5206, 0x6790)
SHENLUN_MATERIAL = _u(0x7ED9, 0x5B9A, 0x8D44, 0x6599)
SHENLUN_REQUIREMENT = _u(0x4F5C, 0x7B54, 0x8981, 0x6C42)
ACCORDING_TO = _u(0x6839, 0x636E)
BELOW = _u(0x4E0B, 0x5217)
MATERIAL = _u(0x6750, 0x6599)
YEAR = _u(0x5E74)
TABLE = _u(0x8868)
FIGURE = _u(0x56FE)
NOTE_CHAR = _u(0x6CE8)


class XingceCleaner:
    """Extract Xingce questions while preserving source positions for image layout."""

    QUESTION_NUM_RE = re.compile(r"^\s*(\d+)\s*[\.\uff0e\u3001\u3002]\s*")
    OPTION_RE = re.compile(r"^\s*([A-D])\s*[\.\uff0e\)\uff09]\s*")
    INLINE_OPTION_RE = re.compile(r"([A-D])\s*[\.\uff0e\)\uff09]\s*")
    SECTION_RE = re.compile(r"^\s*[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\s*[\.\uff0e\u3001\u3002]\s*")

    DEFAULT_SECTION_PATTERNS = (
        r"^\u7b2c\s*[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\s*\u90e8\u5206\s*.*$",
        r"^(?:\u653f\u6cbb\u7406\u8bba|\u5e38\u8bc6\u5224\u65ad|\u653f\u6cbb\u7406\u8bba[+\uff0b\u5341]\u5e38\u8bc6\u5224\u65ad|\u8a00\u8bed\u7406\u89e3(?:\u4e0e\u8868\u8fbe)?|\u6570\u91cf\u5173\u7cfb|\u5224\u65ad\u63a8\u7406|\u8d44\u6599\u5206\u6790)$",
        r"^(?:\u653f\u6cbb\u7406\u8bba|\u5e38\u8bc6\u5224\u65ad|\u8a00\u8bed\u7406\u89e3(?:\u4e0e\u8868\u8fbe)?|\u6570\u91cf\u5173\u7cfb|\u5224\u65ad\u63a8\u7406|\u8d44\u6599\u5206\u6790)\s*[\uff08\(]?\s*\u5171\s*\d+\s*\u9898\s*[\uff09\)]?$",
        r"^[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\s*[\u3001\.\uff0e\u3002]\s*.+$",
        r"^\u6700\u6070\u5f53\u7684\u7b54\u6848",
        r"^绗琝\s*.*閮ㄥ垎.*$",
        r"^(?:鏀挎不鐞嗚.*|甯歌瘑鍒ゆ柇|瑷.*|鏁伴噺鍏崇郴|鍒ゆ柇鎺ㄧ悊|璧勬枡鍒嗘瀽).*$",
        r"^鏈€鎭板綋鐨勭瓟妗.*",
    )
    DEFAULT_FILTER_PATTERNS = (
        r"^[\u203b\*]+\s*\u7b2c\s*[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\s*\u90e8\u5206\u7ed3\u675f.*$",
        r"^[\u203b\*]+$",
        r"^[\uff08\(]?\s*\u5171\s*\d+\s*\u9898\s*[\uff09\)]?$",
        r"^\u5171\s*\d+\s*\u9898$",
        r"^\u53c2\u8003\u65f6\u95f4\s*[:\uff1a]\s*\d+\s*\u5206\u949f$",
    )

    def __init__(self):
        self._section_patterns = self._load_section_patterns()
        self._filter_patterns = self._load_filter_patterns()

    def clean(self, doc: ParsedDocument, progress: Callable[[int, str], None] = None) -> CleanedDocument:
        filtered_out: list[str] = []
        visual_regions_by_page = self._collect_visual_regions(doc)

        pdf_doc = None
        if doc.metadata.get("file_path"):
            import fitz
            pdf_doc = fitz.open(doc.metadata.get("file_path", ""))

        all_lines: list[tuple] = []
        in_data_analysis = False
        for i, page in enumerate(doc.pages):
            if progress:
                progress(int((i + 1) / len(doc.pages) * 100), "清洗中")

            if pdf_doc and i < pdf_doc.page_count:
                page_lines = self._extract_positioned_lines(pdf_doc[i])
            else:
                sorted_blocks = sorted(page.blocks, key=lambda b: (round(b.bbox[1], 1), b.bbox[0]))
                page_lines = [(b.text, b.bbox[1], b.bbox[0]) for b in sorted_blocks]

            for item in page_lines:
                line, y_mm = item[0], item[1]
                x_mm = item[2] if len(item) > 2 else 0.0
                stripped = line.strip()
                if not stripped:
                    continue
                if self._is_filtered_line(stripped):
                    filtered_out.append(f"[configured-filter] {stripped[:50]}")
                    continue
                if self._is_data_analysis_heading(stripped):
                    in_data_analysis = True
                if in_data_analysis and self._is_inside_visual_region(
                    stripped, y_mm, x_mm, visual_regions_by_page.get(page.page_number, [])
                ):
                    filtered_out.append(f"[data-analysis-visual-text] {stripped[:50]}")
                    continue

                is_section_instruction = self._is_section_instruction(stripped)
                if y_mm < HEADER_CUTOFF_MM or y_mm > min(FOOTER_START_MM, page.height_mm - 12):
                    is_content_line = (
                        self._is_content_line_near_header(stripped, y_mm)
                        if y_mm < HEADER_CUTOFF_MM
                        else self._is_content_line_near_footer(stripped, y_mm, page.height_mm)
                    )
                    if not is_section_instruction and not is_content_line:
                        filtered_out.append(f"[header-footer] {stripped[:50]}")
                        continue

                if self._is_page_number(stripped):
                    filtered_out.append(f"[page-number] {stripped[:50]}")
                    continue

                if is_section_instruction:
                    all_lines.append((SECTION_MARKER, stripped, page.page_number, y_mm, x_mm))
                    continue

                all_lines.append((stripped, page.page_number, y_mm, x_mm))

        if pdf_doc:
            pdf_doc.close()

        questions = self._extract_questions(all_lines)
        self._annotate_question_ranges(questions)
        self._annotate_data_analysis_questions(questions)
        for idx, q in enumerate(questions):
            q.number = idx + 1

        return CleanedDocument(exam_type="xingce", questions=questions, filtered_out=filtered_out)

    @staticmethod
    def _extract_positioned_lines(page) -> list[tuple[str, float, float]]:
        page_dict = page.get_text("dict", sort=False)
        lines: list[tuple[str, float, float]] = []
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [span.get("text", "") for span in line.get("spans", [])]
                text = "".join(spans).strip()
                if not text:
                    continue
                bbox = line.get("bbox", (0, 0, 0, 0))
                x_mm = bbox[0] * 25.4 / 72
                y_mm = bbox[1] * 25.4 / 72
                lines.append((text, y_mm, x_mm))
        lines.sort(key=lambda item: (round(item[1], 1), item[2]))
        return lines

    @staticmethod
    def _is_content_line_near_header(text: str, y_mm: float) -> bool:
        if y_mm < 18.0:
            return False
        return bool(XingceCleaner.QUESTION_NUM_RE.match(text) or XingceCleaner.SECTION_RE.match(text))

    @staticmethod
    def _is_content_line_near_footer(text: str, y_mm: float, page_height_mm: float) -> bool:
        if y_mm > page_height_mm - 12.0:
            return False
        stripped = (text or "").strip()
        if not stripped:
            return False
        if XingceCleaner.QUESTION_NUM_RE.match(stripped) or XingceCleaner.OPTION_RE.match(stripped):
            return True
        if XingceCleaner._is_page_number(stripped):
            return False
        return len(stripped) >= 12

    @staticmethod
    def _is_page_number(text: str) -> bool:
        return bool(
            re.match(r"^\s*\u7b2c\s*\d+\s*\u9875\s*$", text)
            or re.match(r"^\s*\u5171\s*\d+\s*\u9875\s*$", text)
            or (re.match(r"^[-\u2014\u2013]?\s*\d{1,3}\s*[-\u2014\u2013]?\s*$", text) and len(text) < 8)
        )

    def _is_section_instruction(self, text: str) -> bool:
        normalized = self._normalize_instruction_text(text)
        return any(pattern.search(normalized) for pattern in self._section_patterns)

    def _is_filtered_line(self, text: str) -> bool:
        normalized = self._normalize_instruction_text(text)
        return any(pattern.search(normalized) for pattern in self._filter_patterns)

    @staticmethod
    def _is_data_analysis_heading(text: str) -> bool:
        compact = re.sub(r"\s+", "", text or "")
        return DATA_ANALYSIS in compact or "璧勬枡鍒嗘瀽" in compact

    @staticmethod
    def _is_inside_visual_region(text: str, y_mm: float, x_mm: float, regions: list[tuple[float, float, float, float]]) -> bool:
        if not regions or not text:
            return False
        question_like = re.match(r"^\s*(\d{1,3})\s*[\.\uff0e\u3001\u3002](?!\d)", text)
        if question_like or XingceCleaner.OPTION_RE.match(text):
            return False
        if XingceCleaner._looks_like_meaningful_content(text):
            return False
        for x0, y0, x1, y1 in regions:
            if y0 - 1.5 <= y_mm <= y1 + 1.5 and x0 - 2.0 <= x_mm <= x1 + 2.0:
                return True
        return False

    @staticmethod
    def _looks_like_meaningful_content(text: str) -> bool:
        """Check if text inside a visual region is meaningful data-analysis content that should be preserved."""
        compact = re.sub(r"\s+", "", text.strip())
        if not compact:
            return False
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", compact))
        # Table headers or short material text (e.g. "\u4f01\u4e1a\u603b\u6570", "\u884c\u4e1a\u540d\u79f0")
        if cjk_count >= 3:
            return True
        # Short pure-CJK table labels (e.g. "\u4e1c\u76df", "\u65e5\u672c", "\u884c\u4e1a", "\u603b\u8ba1")
        if cjk_count >= 2 and len(compact) == cjk_count:
            return True
        # Table/figure captions
        if compact.startswith((TABLE, FIGURE)):
            return True
        # Note text
        if compact.startswith(NOTE_CHAR):
            return True
        # Year patterns like "2024\u5e74"
        if re.match(r"^(?:19|20)\d{2}" + re.escape(YEAR), compact):
            return True
        # Table data: CJK mixed with digits (e.g. "\u571f\u6728\u5de5\u7a0b\u5efa\u7b51")
        if cjk_count >= 2 and re.search(r"\d", compact):
            return True
        # Table units / parenthesized items (e.g. "\uff08\u5bb6\uff09", "\uff08\u4ebf\u5143\uff09")
        if re.match(r"^[\uff08\(][^\)\uff09]+[\uff09\)]$", compact):
            return True
        # Numeric table data cells (e.g. "123.45", "-5.6%")
        if re.match(r"^[-\u2014\u2013]?\s*\d[\d,.]*\s*%?\s*$", compact):
            return True
        # Text >= 15 chars total \u2014 unlikely to be just chart rendering noise
        if len(compact) >= 15:
            return True
        return False

    @classmethod
    def _load_section_patterns(cls) -> list[re.Pattern]:
        return cls._load_patterns("xingce_section_instructions.json", cls.DEFAULT_SECTION_PATTERNS)

    @classmethod
    def _load_filter_patterns(cls) -> list[re.Pattern]:
        return cls._load_patterns("xingce_filter_rules.json", cls.DEFAULT_FILTER_PATTERNS)

    @staticmethod
    def _load_patterns(filename: str, defaults: tuple[str, ...]) -> list[re.Pattern]:
        config_path = resource_path("tools", "pdf_converter", "config", filename)
        patterns = list(defaults)
        try:
            raw = config_path.read_text(encoding="utf-8")
            raw = "\n".join(line for line in raw.splitlines() if not line.strip().startswith("//"))
            configured = json.loads(raw).get("regex_patterns", [])
            if isinstance(configured, list) and configured:
                patterns = [str(item) for item in configured if str(item).strip()]
        except Exception:
            pass
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern))
            except re.error:
                continue
        return compiled or [re.compile(pattern) for pattern in defaults]

    @staticmethod
    def _normalize_instruction_text(text: str) -> str:
        return re.sub(r"\s+", "", (text or "").strip())

    def _extract_questions(self, lines: list[tuple]) -> list[Question]:
        questions: list[Question] = []
        current_q: Question | None = None
        stem_lines: list[str] = []
        current_option: Option | None = None
        pending_sections: list[str] = []
        pending_section_xs: list[float] = []
        pending_section_ys: list[float] = []
        pending_section_pages: list[int] = []
        collecting_section = False
        last_question_num: int | None = None
        last_page: int | None = None
        last_y_mm: float | None = None
        last_x_mm: float | None = None
        pending_source_page: int | None = None
        pending_source_y_mm: float | None = None

        def finish_current_question() -> None:
            nonlocal current_q, stem_lines, current_option, last_question_num, last_x_mm
            if current_q:
                current_q.stem = "\n".join(stem_lines).strip()
                questions.append(current_q)
                last_question_num = current_q.number
                current_q = None
                stem_lines = []
                current_option = None
                last_x_mm = None

        for item in lines:
            if item[0] == SECTION_MARKER:
                finish_current_question()
                pending_sections.append(item[1])
                pending_section_xs.append(item[4] if len(item) > 4 else 0.0)
                pending_section_ys.append(item[3] if len(item) > 3 else 0.0)
                pending_section_pages.append(item[2] if len(item) > 2 else 0)
                if pending_source_page is None:
                    pending_source_page = item[2] if len(item) > 2 else pending_source_page
                    pending_source_y_mm = item[3] if len(item) > 3 else pending_source_y_mm
                collecting_section = True
                continue

            line = item[0]
            current_page = item[1]
            y_mm = item[2] if len(item) > 2 else 0.0
            x_mm = item[3] if len(item) > 3 else 0.0

            q_match = self.QUESTION_NUM_RE.match(line)
            if q_match and self._is_next_question_number(q_match, current_q, last_question_num):
                finish_current_question()
                q_num = int(q_match.group(1))
                stem_start = q_match.end()
                stem_lines = [line[stem_start:].strip()] if line[stem_start:].strip() else []
                current_option = None
                current_q = Question(number=q_num, stem="", source_page=current_page)
                current_q.source_y_mm = y_mm
                if pending_sections:
                    current_q.section_heading = "\n".join(pending_sections)
                    current_q.section_line_xs = list(pending_section_xs)
                    current_q.section_line_ys = list(pending_section_ys)
                    current_q.section_line_pages = list(pending_section_pages)
                    current_q.section_source_page = pending_source_page or current_page
                    current_q.section_source_y_mm = pending_source_y_mm if pending_source_y_mm is not None else y_mm
                    current_q.section_end_page = current_page
                    current_q.section_end_y_mm = y_mm
                    pending_sections = []
                    pending_section_xs = []
                    pending_section_ys = []
                    pending_section_pages = []
                    pending_source_page = None
                    pending_source_y_mm = None
                collecting_section = False
                last_page, last_y_mm, last_x_mm = current_page, y_mm, x_mm
                continue

            if collecting_section:
                pending_sections.append(line)
                pending_section_xs.append(x_mm)
                pending_section_ys.append(y_mm)
                pending_section_pages.append(current_page)
                last_page, last_y_mm, last_x_mm = current_page, y_mm, x_mm
                continue

            inline_options = self._split_inline_options(line)
            if inline_options and current_q:
                for label, text in inline_options:
                    current_option = Option(label=label, text=text)
                    current_q.options.append(current_option)
                last_page, last_y_mm, last_x_mm = current_page, y_mm, x_mm
                continue

            if self._starts_new_material_after_options(
                line, current_q, current_option, current_page, y_mm, x_mm, last_page, last_y_mm
            ):
                finish_current_question()
                pending_sections.append(line)
                pending_section_xs = [x_mm]
                pending_section_ys = [y_mm]
                pending_section_pages = [current_page]
                pending_source_page = current_page
                pending_source_y_mm = y_mm
                collecting_section = True
                last_page, last_y_mm, last_x_mm = current_page, y_mm, x_mm
                continue

            if current_q:
                # After all 4 options are collected, lines from pages 2+ beyond
                # the question's source page are likely watermark/ad content,
                # not exam material. Skip them to prevent pollution.
                if len(current_q.options) >= 4 and current_page - current_q.source_page >= 2:
                    last_page, last_y_mm, last_x_mm = current_page, y_mm, x_mm
                    continue
                if current_option:
                    current_option.text = self._append_option_continuation(
                        current_option.text, line, current_page, y_mm, x_mm, last_page, last_y_mm, last_x_mm
                    )
                else:
                    stem_lines.append(line)
                last_page, last_y_mm, last_x_mm = current_page, y_mm, x_mm

        finish_current_question()
        return questions

    @classmethod
    def _split_inline_options(cls, line: str) -> list[tuple[str, str]]:
        matches = list(cls.INLINE_OPTION_RE.finditer(line or ""))
        if not matches or line[:matches[0].start()].strip():
            return []
        labels = [match.group(1) for match in matches]
        if labels != sorted(labels) or len(set(labels)) != len(labels):
            return []
        options: list[tuple[str, str]] = []
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
            options.append((match.group(1), line[match.end():end].strip()))
        return options

    @staticmethod
    def _append_option_continuation(
        current_text: str,
        line: str,
        current_page: int,
        y_mm: float,
        x_mm: float,
        last_page: int | None,
        last_y_mm: float | None,
        last_x_mm: float | None,
    ) -> str:
        if not current_text:
            return line
        same_source_line = (
            last_page == current_page
            and last_y_mm is not None
            and abs(y_mm - last_y_mm) <= 1.2
            and last_x_mm is not None
            and x_mm > last_x_mm + 8.0
        )
        if same_source_line and not current_text.endswith(" "):
            return f"{current_text}  {line}"
        return f"{current_text}{line}"

    @staticmethod
    def _starts_new_material_after_options(
        line: str,
        current_q: Question | None,
        current_option: Option | None,
        current_page: int,
        y_mm: float,
        x_mm: float,
        last_page: int | None,
        last_y_mm: float | None,
    ) -> bool:
        if not current_q or not current_option or current_option.label != "D":
            return False
        if [option.label for option in current_q.options] != ["A", "B", "C", "D"]:
            return False
        if re.match(r"^\s*(?:\d+|[A-D])\s*[\.\uff0e\u3001\u3002\)\uff09]", line):
            return False
        if current_option.text.rstrip().endswith(("，", "、", "；", "：", "（", "(", "-", "--")):
            return False
        if XingceCleaner._looks_like_material_start(line):
            return True
        if last_page == current_page and last_y_mm is not None and y_mm - last_y_mm < 9.0:
            return False
        if last_page != current_page:
            if XingceCleaner._looks_like_material_start(line):
                return True
            return x_mm <= 35.0 and XingceCleaner._looks_like_material_content(line)
        return x_mm <= 35.0 and XingceCleaner._looks_like_material_content(line)

    @staticmethod
    def _looks_like_material_start(line: str) -> bool:
        compact = re.sub(r"\s+", "", line or "")
        if not compact:
            return False
        if compact.startswith((ACCORDING_TO, BELOW, MATERIAL, TABLE, FIGURE)):
            return True
        if re.match(r"^(?:19|20)\d{2}" + re.escape(YEAR), compact):
            return True
        return False

    @staticmethod
    def _looks_like_material_content(line: str) -> bool:
        compact = re.sub(r"\s+", "", line or "")
        if len(compact) < 10:
            return False
        if XingceCleaner.QUESTION_NUM_RE.match(compact) or XingceCleaner.OPTION_RE.match(compact):
            return False
        if not re.search(r"[\u4e00-\u9fff]", compact):
            return False
        return True

    @staticmethod
    def _is_next_question_number(match: re.Match, current_q: Question | None, last_question_num: int | None = None) -> bool:
        q_num = int(match.group(1))
        if q_num <= 0:
            return False
        baseline = current_q.number if current_q is not None else last_question_num
        if baseline is None:
            return True
        return baseline < q_num <= baseline + 3

    @staticmethod
    def _annotate_question_ranges(questions: list[Question]) -> None:
        for idx, question in enumerate(questions):
            next_q = questions[idx + 1] if idx + 1 < len(questions) else None
            if not next_q:
                question.source_end_page = None
                question.source_end_y_mm = None
                continue
            question.source_end_page = getattr(next_q, "section_source_page", None) or getattr(next_q, "source_page", None)
            question.source_end_y_mm = getattr(next_q, "section_source_y_mm", None)
            if question.source_end_y_mm is None:
                question.source_end_y_mm = getattr(next_q, "source_y_mm", None)

    @staticmethod
    def _annotate_data_analysis_questions(questions: list[Question]) -> None:
        in_data_analysis = False
        for question in questions:
            heading = getattr(question, "section_heading", "") or ""
            if DATA_ANALYSIS in re.sub(r"\s+", "", heading) or "璧勬枡鍒嗘瀽" in re.sub(r"\s+", "", heading):
                in_data_analysis = True
            if in_data_analysis:
                question.is_data_analysis = True

    @staticmethod
    def _collect_visual_regions(doc: ParsedDocument) -> dict[int, list[tuple[float, float, float, float]]]:
        regions: dict[int, list[tuple[float, float, float, float]]] = {}
        drawn_regions = XingceCleaner._extract_all_drawn_table_regions(doc.metadata.get("file_path", ""))
        for page in doc.pages:
            page_regions = [img.bbox for img in page.images]
            page_regions.extend(drawn_regions.get(page.page_number, []))
            if page_regions:
                regions[page.page_number] = XingceCleaner._merge_regions(page_regions)
        return regions

    @staticmethod
    def _extract_all_drawn_table_regions(file_path: str) -> dict[int, list[tuple[float, float, float, float]]]:
        if not file_path:
            return {}
        try:
            import fitz
            output: dict[int, list[tuple[float, float, float, float]]] = {}
            with fitz.open(file_path) as pdf_doc:
                for page_index, page in enumerate(pdf_doc, start=1):
                    rects = []
                    for drawing in page.get_drawings():
                        rect = drawing.get("rect")
                        if not rect:
                            continue
                        x0, y0, x1, y1 = (v * 25.4 / 72 for v in (rect.x0, rect.y0, rect.x1, rect.y1))
                        if x1 - x0 < 20 and y1 - y0 < 20:
                            continue
                        rects.append((x0, y0, x1, y1))
                    if rects:
                        output[page_index] = XingceCleaner._merge_regions(rects)
            return output
        except Exception:
            return {}

    @staticmethod
    def _merge_regions(regions: list[tuple[float, float, float, float]]) -> list[tuple[float, float, float, float]]:
        merged: list[tuple[float, float, float, float]] = []
        for region in sorted(regions, key=lambda r: (r[1], r[0])):
            x0, y0, x1, y1 = region
            found = False
            for idx, existing in enumerate(merged):
                ex0, ey0, ex1, ey1 = existing
                overlaps = not (x1 < ex0 - 2 or x0 > ex1 + 2 or y1 < ey0 - 2 or y0 > ey1 + 2)
                same_grid = abs(y0 - ey0) < 90 and abs(y1 - ey1) < 90 and x0 <= ex1 + 3 and x1 >= ex0 - 3
                if overlaps or same_grid:
                    merged[idx] = (min(x0, ex0), min(y0, ey0), max(x1, ex1), max(y1, ey1))
                    found = True
                    break
            if not found:
                merged.append(region)
        return merged


def detect_exam_type(doc: ParsedDocument) -> str:
    import fitz

    xingce_score = 0
    shenlun_score = 0
    filepath = doc.metadata.get("file_path", "")
    if filepath:
        try:
            pdf_doc = fitz.open(filepath)
            for page in pdf_doc:
                text = page.get_text("text", sort=True)
                if re.search(r"[A-D]\s*[\.\uff0e\)\uff09]", text):
                    xingce_score += 1
                if SHENLUN_MATERIAL in text or SHENLUN_REQUIREMENT in text:
                    shenlun_score += 2
            pdf_doc.close()
        except Exception:
            pass
    return "shenlun" if shenlun_score > xingce_score else "xingce"
