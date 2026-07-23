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
    OPTION_RE = re.compile(r"^\s*([A-D])\s*[\.\uff0e\u3002_\-\u2014\u4e00\)\uff09]\s*")
    INLINE_OPTION_RE = re.compile(r"([A-D])\s*[\.\uff0e\u3002_\-\u2014\u4e00\)\uff09]\s*")
    SECTION_RE = re.compile(r"^\s*[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\s*[\.\uff0e\u3001\u3002]\s*")

    DEFAULT_SECTION_PATTERNS = (
        r"^\u7b2c\s*[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\s*\u90e8\u5206\s*.*$",
        r"^(?:\u653f\u6cbb\u7406\u8bba|\u5e38\u8bc6\u5224\u65ad|\u653f\u6cbb\u7406\u8bba[+\uff0b\u5341]\u5e38\u8bc6\u5224\u65ad|\u8a00\u8bed\u7406\u89e3(?:\u4e0e\u8868\u8fbe)?|\u6570\u91cf\u5173\u7cfb|\u5224\u65ad\u63a8\u7406|\u8d44\u6599\u5206\u6790)$",
        r"^(?:\u653f\u6cbb\u7406\u8bba|\u5e38\u8bc6\u5224\u65ad|\u8a00\u8bed\u7406\u89e3(?:\u4e0e\u8868\u8fbe)?|\u6570\u91cf\u5173\u7cfb|\u5224\u65ad\u63a8\u7406|\u8d44\u6599\u5206\u6790)\s*[\uff08\(]?\s*\u5171\s*\d+\s*\u9898\s*[\uff09\)]?$",
        r"^[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\s*[\u3001\.\uff0e\u3002]\s*.+$",
        r"^\u6700\u6070\u5f53\u7684\u7b54\u6848",
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
                is_scanned_question_number = (
                    doc.source_type == "image"
                    and re.fullmatch(r"\d{1,3}", stripped)
                    and x_mm <= 38.0
                    and HEADER_CUTOFF_MM <= y_mm <= min(FOOTER_START_MM, page.height_mm - 12)
                )
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
                    if not is_scanned_question_number and not is_section_instruction and not is_content_line:
                        filtered_out.append(f"[header-footer] {stripped[:50]}")
                        continue

                if not is_scanned_question_number and self._is_page_number(stripped):
                    filtered_out.append(f"[page-number] {stripped[:50]}")
                    continue

                if is_section_instruction:
                    all_lines.append((SECTION_MARKER, stripped, page.page_number, y_mm, x_mm))
                    continue

                all_lines.append((stripped, page.page_number, y_mm, x_mm))

        if doc.source_type == "image":
            all_lines = self._normalize_scanned_lines(all_lines)

        # Separate answer comparison tables from exam content.
        # Uses density clustering of answer-grid lines so it is robust
        # against OCR errors in section titles.
        exam_lines, answer_groups = self._split_answer_sections(all_lines)

        if pdf_doc:
            pdf_doc.close()

        questions = self._extract_questions(exam_lines)
        self._annotate_question_ranges(questions)
        self._annotate_data_analysis_questions(questions)
        # Keep original question numbers from the PDF — each section
        # (演练一, 实战演练二, ...) has its own independent numbering.

        # Map each answer cluster to the 1-based question count it
        # follows (NOT the question number, which restarts per section).
        # Using count avoids dict-key collisions when multiple sections
        # have identically numbered questions (e.g. Q30 in each 演练).
        answer_sections: list[tuple[int, list[str]]] = []
        for pos, group in answer_groups:
            if pos <= 0:
                after_count = 0
            else:
                before_qs = self._extract_questions(list(exam_lines[:pos]))
                after_count = len(before_qs)
            text_lines = self._extract_answer_section_text(group)
            if text_lines:
                answer_sections.append((after_count, text_lines))

        return CleanedDocument(
            exam_type="xingce",
            questions=questions,
            filtered_out=filtered_out,
            answer_sections=answer_sections,
        )

    @staticmethod
    def _replace_blank_markers(text: str) -> str:
        """将 PDF 中的空白占位符（\xa0）替换为可见下划线。"""
        return text.replace('\xa0', '__')

    @staticmethod
    def _extract_positioned_lines(page) -> list[tuple[str, float, float]]:
        page_dict = page.get_text("rawdict", sort=False)
        lines: list[tuple[str, float, float]] = []
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = XingceCleaner._join_line_chars(line)
                text = XingceCleaner._replace_blank_markers(text).strip()
                if not text:
                    continue
                bbox = line.get("bbox", (0, 0, 0, 0))
                x_mm = bbox[0] * 25.4 / 72
                y_mm = bbox[1] * 25.4 / 72
                lines.append((text, y_mm, x_mm))
        lines.sort(key=lambda item: (round(item[1], 1), item[2]))
        return lines

    @staticmethod
    def _join_line_chars(line: dict) -> str:
        """Join a rawdict line's chars, restoring word gaps as spaces.

        Some PDFs render the separation between option words (e.g. idiom
        pairs in 逻辑填空 options like "束手就擒 一探究竟") as a glyph-position
        displacement instead of a real space character, so the extracted
        span text arrives with the words glued together. Detect horizontal
        gaps wider than 0.3 em between adjacent glyphs and insert a space
        so the words stay separated downstream.
        """
        direction = line.get("dir", (1, 0))
        horizontal = abs(direction[0]) >= 0.7
        parts: list[str] = []
        prev_x1: float | None = None
        for span in line.get("spans", []):
            size = span.get("size", 10.0) or 10.0
            for char in span.get("chars", []):
                c = char.get("c", "")
                bbox = char.get("bbox")
                if (horizontal and bbox and prev_x1 is not None
                        and c != " " and parts and parts[-1] != " "
                        and bbox[0] - prev_x1 >= size * 0.3):
                    parts.append(" ")
                if bbox:
                    prev_x1 = bbox[2]
                parts.append(c)
        return "".join(parts)

    @staticmethod
    def _is_content_line_near_header(text: str, y_mm: float) -> bool:
        # Question numbers, option labels, and section markers at any
        # Y position are exam content — never header/watermark noise.
        if (XingceCleaner.QUESTION_NUM_RE.match(text)
                or XingceCleaner.OPTION_RE.match(text)
                or XingceCleaner.SECTION_RE.match(text)):
            return True
        # Long CJK text (>=15 chars) near the page top is exam content,
        # not a header/watermark — real headers are short ("版权所有",
        # "第X页", etc.).
        compact = re.sub(r"\s+", "", text)
        if len(compact) >= 15:
            return True
        if y_mm < 12.0:
            return False
        return False

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
        return DATA_ANALYSIS in compact

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
        """Check if text inside a visual region is meaningful content that should be preserved.

        Only structural markers (table/figure captions, notes, year-marked text)
        and longer text (>=15 chars) are preserved. Short labels, numbers, and
        table cell data inside visual regions are treated as chart noise and
        filtered out.
        """
        compact = re.sub(r"\s+", "", text.strip())
        if not compact:
            return False
        # Table/figure captions (e.g. "\u88681 2022\u5e74...", "\u56fe \u589e\u957f\u7387")
        if compact.startswith((TABLE, FIGURE)):
            return True
        # Note text (e.g. "\u6ce8\uff1a...")
        if compact.startswith(NOTE_CHAR):
            return True
        # Year-marked text with substantial content after the year
        # (e.g. "2024\u5e74\u4e2d\u5173\u6751...").  Bare year labels like "2022\u5e74" that
        # serve as table column headers are excluded.
        if re.match(r"^(?:19|20)\d{2}" + re.escape(YEAR) + r".{3,}", compact):
            return True
        # Text >= 20 chars total \u2014 long enough to be a real material sentence,
        # not a table-row label (which rarely exceeds 18 chars).
        if len(compact) >= 20:
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

    @classmethod
    def _normalize_scanned_lines(cls, lines: list[tuple]) -> list[tuple]:
        """Repair common OCR splits before question extraction.

        Scanned PDFs often recognize left-margin question numbers as bare
        "2" instead of "2.", and option labels as standalone "C" with
        the option body in a nearby block on the same visual row.
        """
        normalized: list[tuple] = []
        sorted_lines = lines
        first_content = cls._first_scanned_content_line(sorted_lines)
        first_marker = cls._first_scanned_question_marker(sorted_lines)
        if cls._needs_synthetic_first_question(first_content, first_marker):
            normalized.append(("1.", first_content[1], first_content[2], min(first_content[3], 29.0)))
        index = 0
        while index < len(sorted_lines):
            item = sorted_lines[index]
            if item[0] == SECTION_MARKER:
                normalized.append(item)
                index += 1
                continue

            text = str(item[0]).strip()
            page = item[1]
            y_mm = item[2] if len(item) > 2 else 0.0
            x_mm = item[3] if len(item) > 3 else 0.0

            if re.fullmatch(r"\d{1,3}", text) and x_mm <= 38.0:
                normalized.append((f"{text}.", page, y_mm, x_mm))
                index += 1
                continue

            leading_num = re.match(r"^(\d{1,3})\s+(.+)$", text)
            if leading_num and x_mm <= 38.0:
                q_num = int(leading_num.group(1))
                if 1 <= q_num <= 200:
                    normalized.append((f"{q_num}. {leading_num.group(2).strip()}", page, y_mm, x_mm))
                    index += 1
                    continue

            label_match = re.fullmatch(r"([A-D])\s*[_\-—一.]?", text)
            if label_match and x_mm <= 38.0:
                merged = cls._merge_scanned_option_label(label_match.group(1), item, sorted_lines, index)
                if merged:
                    normalized.append(merged[0])
                    index = merged[1]
                    continue

            inferred_label = cls._infer_missing_option_label(item, sorted_lines, index)
            if inferred_label:
                normalized.append((f"{inferred_label}.{text}", page, y_mm, x_mm))
                index += 1
                continue

            normalized.append(item)
            index += 1

        return normalized

    @classmethod
    def _merge_scanned_option_label(cls, label: str, item: tuple, lines: list[tuple], index: int) -> tuple[tuple, int] | None:
        page = item[1]
        y_mm = item[2] if len(item) > 2 else 0.0
        x_mm = item[3] if len(item) > 3 else 0.0
        bodies: list[str] = []
        next_index = index + 1
        while next_index < len(lines):
            candidate = lines[next_index]
            if candidate[0] == SECTION_MARKER:
                break
            cand_page = candidate[1]
            cand_y = candidate[2] if len(candidate) > 2 else 0.0
            cand_x = candidate[3] if len(candidate) > 3 else 0.0
            cand_text = str(candidate[0]).strip()
            if cand_page != page or abs(cand_y - y_mm) > 2.0:
                break
            if cand_x <= x_mm + 2.0:
                break
            if cls.QUESTION_NUM_RE.match(cand_text) or re.fullmatch(r"\d{1,3}", cand_text):
                break
            bodies.append(cand_text)
            next_index += 1

        if not bodies:
            return None
        return (f"{label}.{' '.join(bodies)}", page, y_mm, x_mm), next_index

    @classmethod
    def _first_scanned_question_marker(cls, lines: list[tuple]) -> tuple | None:
        for item in lines:
            if item[0] == SECTION_MARKER:
                continue
            text = str(item[0]).strip()
            x_mm = item[3] if len(item) > 3 else 0.0
            if x_mm > 38.0:
                continue
            if cls.QUESTION_NUM_RE.match(text) or re.fullmatch(r"\d{1,3}", text):
                return item
            if re.match(r"^(\d{1,3})\s+.+$", text):
                return item
        return None

    @staticmethod
    def _needs_synthetic_first_question(first_content: tuple | None, first_marker: tuple | None) -> bool:
        if not first_content:
            return False
        if not first_marker:
            return True
        content_page = first_content[1]
        content_y = first_content[2] if len(first_content) > 2 else 0.0
        marker_page = first_marker[1]
        marker_y = first_marker[2] if len(first_marker) > 2 else 0.0
        return marker_page > content_page or (marker_page == content_page and marker_y - content_y > 18.0)

    @staticmethod
    def _first_scanned_content_line(lines: list[tuple]) -> tuple | None:
        for item in lines:
            if item[0] == SECTION_MARKER:
                continue
            text = str(item[0]).strip()
            if not text or re.fullmatch(r"\d{1,3}", text):
                continue
            page = item[1]
            y_mm = item[2] if len(item) > 2 else 0.0
            x_mm = item[3] if len(item) > 3 else 0.0
            compact = re.sub(r"\s+", "", text)
            if page == 1 and y_mm > HEADER_CUTOFF_MM and x_mm <= 45.0 and len(compact) >= 10:
                return item
        return None

    @classmethod
    def _infer_missing_option_label(cls, item: tuple, lines: list[tuple], index: int) -> str | None:
        text = str(item[0]).strip()
        if cls.OPTION_RE.match(text) or cls.QUESTION_NUM_RE.match(text):
            return None
        page = item[1]
        y_mm = item[2] if len(item) > 2 else 0.0
        x_mm = item[3] if len(item) > 3 else 0.0
        if x_mm < 48.0 or x_mm > 130.0 or len(re.sub(r"\s+", "", text)) < 6:
            return None
        prev_label = None
        prev_same_row_label = None
        for prev in reversed(lines[:index]):
            if prev[0] == SECTION_MARKER:
                continue
            prev_page = prev[1]
            prev_y = prev[2] if len(prev) > 2 else 0.0
            prev_x = prev[3] if len(prev) > 3 else 0.0
            prev_text = str(prev[0]).strip()
            match = cls.OPTION_RE.match(prev_text)
            if match:
                prev_label = match.group(1)
                if prev_page == page and abs(prev_y - y_mm) <= 2.0 and prev_x < x_mm:
                    prev_same_row_label = prev_label
                    break
            if cls.QUESTION_NUM_RE.match(prev_text):
                break
        if prev_same_row_label == "A":
            return "B"
        if prev_same_row_label == "C":
            return "D"
        return None

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
                # When a section marker immediately follows a question
                # number that has no content yet (e.g. "1.   "), do NOT
                # finalize the empty question — that would create a
                # phantom Q1 and shift all later numbers by +1.
                # Instead, attach the section as the question's heading
                # and keep accumulating subsequent lines as its stem.
                if current_q and not stem_lines and not current_q.options:
                    pending_sections.append(item[1])
                    pending_section_xs.append(item[4] if len(item) > 4 else 0.0)
                    pending_section_ys.append(item[3] if len(item) > 3 else 0.0)
                    pending_section_pages.append(item[2] if len(item) > 2 else 0)
                    if pending_source_page is None:
                        pending_source_page = item[2] if len(item) > 2 else pending_source_page
                        pending_source_y_mm = item[3] if len(item) > 3 else pending_source_y_mm
                    continue
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
                    # Guard: after A+B+C+D are collected, another "A"
                    # starts a new question — prevents Q30 from absorbing
                    # Q31-36's options when answer cluster removal leaves
                    # no clear boundary between question groups.
                    existing = {o.label for o in current_q.options}
                    if len(existing) == 4 and label == "A":
                        finish_current_question()
                        inferred_num = (last_question_num or 0) + 1
                        current_q = Question(
                            number=inferred_num, stem="",
                            source_page=current_page,
                        )
                        current_q.source_y_mm = y_mm
                        stem_lines = []
                        current_option = None
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

            if self._starts_new_scanned_question_without_number(
                line, current_q, current_option, current_page, y_mm, x_mm, last_page, last_y_mm
            ):
                finish_current_question()
                inferred_num = (last_question_num or 0) + 1
                current_q = Question(number=inferred_num, stem="", source_page=current_page)
                current_q.source_y_mm = y_mm
                stem_lines = [line]
                current_option = None
                last_page, last_y_mm, last_x_mm = current_page, y_mm, x_mm
                continue

            # After a question group is finished (current_q is None due to
            # finish_current_question having been called), section headings
            # like "实战演练二" can appear between groups.  Catch them
            # here instead of silently dropping them.
            if current_q is None and not collecting_section and self._looks_like_material_start(line):
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
                    split_continuation = self._split_option_continuation_with_next_labels(line, current_q)
                    if split_continuation:
                        prefix, extra_options = split_continuation
                        if prefix:
                            missing_label = self._next_option_label(current_q)
                            if missing_label and missing_label != current_option.label:
                                current_option = Option(label=missing_label, text=prefix)
                                current_q.options.append(current_option)
                            else:
                                current_option.text = self._append_option_continuation(
                                    current_option.text, prefix, current_page, y_mm, x_mm, last_page, last_y_mm, last_x_mm
                                )
                        for label, text_part in extra_options:
                            current_option = Option(label=label, text=text_part)
                            current_q.options.append(current_option)
                        last_page, last_y_mm, last_x_mm = current_page, y_mm, x_mm
                        continue
                    current_option.text = self._append_option_continuation(
                        current_option.text, line, current_page, y_mm, x_mm, last_page, last_y_mm, last_x_mm
                    )
                else:
                    # If the question was just created (no real stem yet)
                    # and the line looks like a section heading (e.g.
                    # "实战演练一" after a synthetic "1."), promote it to
                    # section_heading instead of appending to stem.
                    # Only match genuine section-heading patterns
                    # (演练/练习/强化/冲刺/真题/模拟), NOT generic text
                    # like "根据…" or "下列…" which can start real stems.
                    stem_so_far = "".join(stem_lines).strip()
                    if (not stem_so_far
                            and not current_q.options
                            and self._looks_like_section_heading(line)):
                        current_q.section_heading = line
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

    @classmethod
    def _split_option_continuation_with_next_labels(cls, line: str, current_q: Question | None) -> tuple[str, list[tuple[str, str]]] | None:
        if not current_q or not current_q.options:
            return None
        matches = list(cls.INLINE_OPTION_RE.finditer(line or ""))
        if not matches:
            return None
        labels = [match.group(1) for match in matches]
        if labels != sorted(labels) or len(set(labels)) != len(labels):
            return None
        prefix = line[:matches[0].start()].strip()
        extra_options: list[tuple[str, str]] = []
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
            extra_options.append((match.group(1), line[match.end():end].strip()))
        existing = {option.label for option in current_q.options}
        if any(label in existing for label, _ in extra_options):
            return None
        return prefix, extra_options

    @staticmethod
    def _next_option_label(current_q: Question | None) -> str | None:
        if not current_q:
            return None
        labels = [option.label for option in current_q.options]
        for label in ("A", "B", "C", "D"):
            if label not in labels:
                return label
        return None

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
    def _starts_new_scanned_question_without_number(
        line: str,
        current_q: Question | None,
        current_option: Option | None,
        current_page: int,
        y_mm: float,
        x_mm: float,
        last_page: int | None,
        last_y_mm: float | None,
    ) -> bool:
        if not current_q or not current_option:
            return False
        if XingceCleaner.OPTION_RE.match(line) or XingceCleaner.QUESTION_NUM_RE.match(line):
            return False
        compact = re.sub(r"\s+", "", line or "")
        if len(compact) < 14 or not re.search(r"[\u4e00-\u9fff]", compact):
            return False
        if x_mm > 45.0:
            return False
        if last_page == current_page and last_y_mm is not None and y_mm - last_y_mm < 7.0:
            return False
        if re.match(r"^(?:19|20)\d{2}", compact):
            return True
        if compact.startswith(("这段文字", "上述材料", "上述文字", "文段")):
            return False
        return len(current_q.options) >= 1 and (last_page != current_page or y_mm - (last_y_mm or y_mm) >= 9.0)

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
        # Section-start markers take priority over option-continuation
        # punctuation checks.  Otherwise a heading like "实战演练二" on
        # the next page is wrongly appended to the D option text.
        if XingceCleaner._looks_like_material_start(line):
            return True
        if current_option.text.rstrip().endswith(("，", "、", "；", "：", "（", "(", "-", "--")):
            return False
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
        # Section-like headings that appear between question groups
        # (e.g. after an answer comparison table): 实战演练二, 模拟演练一
        if re.match(
            r"^(实战演练|模拟演练|强化练习|专项练习|真题演练|巩固练习|综合练习|冲刺练习)",
            compact,
        ):
            return True
        return False

    @staticmethod
    def _looks_like_section_heading(line: str) -> bool:
        """Return True only for genuine section-heading patterns.

        Unlike _looks_like_material_start this does NOT match generic
        text starts like "根据…" or "下列…" — only the dedicated
        section-heading prefixes used in exam PDFs (演练, 练习, etc.).
        """
        compact = re.sub(r"\s+", "", line or "")
        if not compact:
            return False
        if re.match(
            r"^(实战演练|模拟演练|强化练习|专项练习|真题演练|巩固练习|综合练习|冲刺练习)",
            compact,
        ):
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
        # Normal increment within the same section
        if baseline < q_num <= baseline + 3:
            return True
        # Section restart: numbering resets (e.g. 30 → 1 after an
        # answer comparison table between 演练一 and 演练二).
        # Only accepted when q_num is small and baseline is large
        # enough to make a genuine restart plausible.
        if q_num <= 10 and baseline > 10:
            return True
        return False

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
            if DATA_ANALYSIS in re.sub(r"\s+", "", heading):
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
                        # Collect ALL drawings including thin table-border lines.
                        # Individual line segments (e.g. horizontal rules 145mm×0mm,
                        # vertical rules 0mm×50mm) are too thin to pass a per-item
                        # size check, but when merged together they form the bounding
                        # box of the entire table.
                        if x1 - x0 < 0.5 and y1 - y0 < 0.5:
                            continue
                        rects.append((x0, y0, x1, y1))
                    if rects:
                        # Merge thin line segments into larger table regions first,
                        # then filter out regions that are too small to be tables.
                        merged = XingceCleaner._merge_regions(rects)
                        filtered = []
                        for x0, y0, x1, y1 in merged:
                            if x1 - x0 >= 30 and y1 - y0 >= 20:
                                # Expand upward by 15 mm to catch column-group
                                # headers (e.g. "2022年" / "2023年") that sit
                                # above the table border lines.
                                expanded_y0 = max(HEADER_CUTOFF_MM, y0 - 15.0)
                                filtered.append((x0, expanded_y0, x1, y1))
                        if filtered:
                            output[page_index] = filtered
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


    @staticmethod
    def _looks_like_answer_grid_line(text: str) -> bool:
        """Return True if *text* looks like part of an answer comparison grid.

        Typical answer grid rows:
            1-5  ABCDA    6-10  BCDAB
            1.【答案】A
            1-5: A B C D A
            ABCDA  BCDAB  CDABC  DABCD
        """
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return False
        # Number range header: "1-5", "11～20", etc.
        if re.match(r"^\d{1,3}[-~～—]\d{1,3}", compact):
            return True
        # Individual answer: "1.A", "2.【答案】B", "11.C"
        if re.match(r"^\d{1,3}[\.、．]?\s*[【】]?答案[【】]?\s*[A-D]$", compact):
            return True
        if re.match(r"^\d{1,3}[\.、．][A-D]$", compact):
            return True
        # Pure answer-letter sequence (3+ consecutive A-D letters): "ABCDA"
        if re.match(r"^[A-D]{3,}$", compact):
            return True
        # Answer grid with mixed digits and letters (sparse format):
        # "1A2B3C4D5A" or "1.A 2.B 3.C"
        if re.match(r"^(\d{1,3}[\.、．]?\s*[A-D]\s*){3,}$", compact):
            return True
        return False

    @classmethod
    def _split_answer_sections(
        cls, lines: list[tuple]
    ) -> tuple[list[tuple], list[tuple[list[tuple]]]]:
        """Split *lines* into ``(exam_lines, answer_section_groups)``
        using answer-grid density clustering.

        Returns:
            exam_lines: All non-answer-content lines in original order.
            answer_section_groups: List of answer clusters, each is a
            list of ``(text, page, y_mm, x_mm)`` tuples representing one
            answer comparison table.

        Algorithm:
        1. Mark each line as answer-grid-like or not.
        2. Find clusters of 2+ consecutive grid lines.
        3. For each cluster, include the 1 preceding short line
           (potential header like "答案对照表").
        4. Return clusters separately so callers can determine their
           position relative to extracted questions.
        """
        n = len(lines)
        if n == 0:
            return [], []

        # Mark answer-grid lines (skip SECTION_MARKERs)
        is_grid = [False] * n
        for i, item in enumerate(lines):
            if item[0] != SECTION_MARKER:
                is_grid[i] = cls._looks_like_answer_grid_line(
                    str(item[0]).strip()
                )

        # Find clusters of 2+ consecutive grid lines
        in_cluster = [False] * n
        clusters: list[tuple[int, int]] = []  # (start, end) inclusive
        i = 0
        while i < n:
            if is_grid[i]:
                j = i
                while j < n and is_grid[j]:
                    j += 1
                if j - i >= 2:
                    # Expand backward: 1 short line (potential header).
                    # Skip lines that look like section / material starts
                    # (e.g. "实战演练二") — they are exam content, not
                    # answer-table headers, and consuming them here would
                    # drop the section heading from the rendered output.
                    start = i
                    if start > 0 and lines[start - 1][0] != SECTION_MARKER:
                        prev_text = str(lines[start - 1][0]).strip()
                        compact_prev = re.sub(r"\s+", "", prev_text)
                        if len(compact_prev) <= 12 and not cls._looks_like_material_start(prev_text):
                            start -= 1
                    end = j  # exclusive
                    clusters.append((start, end))
                    for k in range(start, end):
                        in_cluster[k] = True
                i = j
            else:
                i += 1

        # Build exam_lines (exclude cluster content)
        exam_lines = [
            item for idx, item in enumerate(lines) if not in_cluster[idx]
        ]

        # Build answer_section_groups, each tagged with its position in
        # *exam_lines* — the number of non-cluster lines before it.
        answer_section_groups: list[tuple[int, list[tuple]]] = []
        for start, end in clusters:
            group = list(lines[start:end])
            if not group:
                continue
            # Position in exam_lines = count of non-cluster lines
            # before the cluster start.
            pos = sum(1 for k in range(start) if not in_cluster[k])
            answer_section_groups.append((pos, group))

        return exam_lines, answer_section_groups

    @staticmethod
    def _extract_answer_section_text(lines: list[tuple]) -> list[str]:
        """Extract readable text from answer section lines.

        Answer grid lines are sorted by their starting number so the
        comparison table reads 1~5, 6~10, 11~15... in order.
        """
        headers: list[str] = []
        grid_lines: list[str] = []

        for item in lines:
            marker_or_text = item[0]
            if marker_or_text == SECTION_MARKER:
                headers.append("")
                headers.append(item[1])
                continue
            text = str(marker_or_text).strip()
            if not text:
                continue
            if XingceCleaner._looks_like_answer_grid_line(text):
                grid_lines.append(text)
            else:
                headers.append(text)

        # Sort grid lines by the first number in each range
        def _sort_key(text: str) -> int:
            import re
            m = re.match(r"^(\d{1,3})", text.replace(" ", ""))
            return int(m.group(1)) if m else 0

        grid_lines.sort(key=_sort_key)

        return headers + grid_lines


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
