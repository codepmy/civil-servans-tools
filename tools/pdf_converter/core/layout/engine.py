from __future__ import annotations

import re
from dataclasses import dataclass

from tools.pdf_converter.core.models import CleanedDocument, Question, PageElement, LaidOutDocument, LaidOutPage, ImageBlock


def _u(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


DATA_ANALYSIS = _u(0x8D44, 0x6599, 0x5206, 0x6790)
GIVEN_MATERIAL = _u(0x7ED9, 0x5B9A, 0x8D44, 0x6599)
ANSWER_REQUIREMENTS = _u(0x4F5C, 0x7B54, 0x8981, 0x6C42)
TABLE_CHAR = _u(0x8868)
FIGURE_CHAR = _u(0x56FE)
NOTE_CHAR = _u(0x6CE8)
QUESTION_PROMPT_PREFIX = _u(0x8BF7, 0x56DE, 0x7B54)


@dataclass
class LayoutConfig:
    name: str = "default"
    exam_type: str = "xingce"

    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    margin_top: float = 25.0
    margin_bottom: float = 20.0
    margin_left: float = 30.0
    margin_right: float = 25.0

    header_font: str = "SimHei"
    header_size: float = 12.0
    header_bold: bool = True

    question_num_font: str = "SimHei"
    question_num_size: float = 10.5
    question_num_bold: bool = True

    stem_font: str = "SimSun"
    stem_size: float = 10.5
    stem_bold: bool = False

    option_font: str = "SimSun"
    option_size: float = 10.5
    option_bold: bool = False

    page_num_font: str = "SimSun"
    page_num_size: float = 9.0
    page_num_bold: bool = False

    line_height_multiplier: float = 1.5
    paragraph_spacing_mm: float = 2.0
    question_spacing_mm: float = 5.0
    option_indent_mm: float = 8.0
    answer_line_length_mm: float = 60.0

    show_answer_line: bool = False
    show_page_number: bool = True

    question_suffix: str = "."
    option_labels: tuple = ("A", "B", "C", "D")
    option_suffix: str = "."

    PAPER_SIZES = {
        "A4": (210, 297), "B5": (176, 250),
        "A3": (297, 420), "B4": (250, 353), "16k": (185, 260),
        "16寮€": (185, 260),
    }

    @classmethod
    def from_template(cls, template: dict, overrides: dict | None = None) -> "LayoutConfig":
        o = overrides or {}
        page = template.get("page", {})
        margins = page.get("margins", {})
        fonts = template.get("fonts", {})
        spacing = template.get("spacing", {})
        numbering = template.get("numbering", {})

        stem = fonts.get("question_stem", {})
        qn = fonts.get("question_number", {})
        opt = fonts.get("option", {})
        header = fonts.get("header", {})
        pn = fonts.get("page_number", {})

        ps = o.get("page_size", "")
        if ps and ps in cls.PAPER_SIZES:
            pw, ph = cls.PAPER_SIZES[ps]
        else:
            pw, ph = page.get("width_mm", 210), page.get("height_mm", 297)

        return cls(
            name=template.get("name", ""),
            exam_type=template.get("exam_type", "xingce"),
            page_width_mm=pw, page_height_mm=ph,
            margin_top=o.get("margin_top", margins.get("top_mm", 25)),
            margin_bottom=o.get("margin_bottom", margins.get("bottom_mm", 20)),
            margin_left=o.get("margin_left", margins.get("left_mm", 30)),
            margin_right=o.get("margin_right", margins.get("right_mm", 25)),
            header_font=o.get("header_font", header.get("family", "SimHei")),
            header_size=o.get("header_size", header.get("size_pt", 12)),
            question_num_font=o.get("num_font", qn.get("family", "SimHei")),
            question_num_size=qn.get("size_pt", 10.5),
            stem_font=o.get("body_font", stem.get("family", "SimSun")),
            stem_size=o.get("body_size", stem.get("size_pt", 10.5)),
            option_font=o.get("opt_font", opt.get("family", "SimSun")),
            option_size=o.get("opt_size", opt.get("size_pt", 10.5)),
            page_num_font=pn.get("family", "SimSun"),
            page_num_size=pn.get("size_pt", 9),
            line_height_multiplier=o.get("line_spacing", spacing.get("line_height_multiplier", 1.5)),
            question_spacing_mm=o.get("question_spacing", spacing.get("question_spacing_mm", 5.0)),
            option_indent_mm=o.get("option_indent", spacing.get("option_indent_mm", 8.0)),
            show_answer_line=o.get("show_answer_line", False),
            show_page_number=o.get("show_page_number", True),
            question_suffix=numbering.get("question_suffix", "."),
            option_suffix=numbering.get("option_suffix", "."),
        )


class LayoutEngine:
    def __init__(self, config: LayoutConfig):
        self.config = config
        self._pages: list[LaidOutPage] = []
        self._current_page: LaidOutPage | None = None
        self._current_y: float = 0.0
        self._images_by_page: dict[int, list[ImageBlock]] = {}
        self._page_questions: dict[int, list[Question]] = {}

    def layout(self, doc: CleanedDocument, images: list[ImageBlock] | None = None) -> LaidOutDocument:
        self._pages = []
        self._new_page()
        self._images_by_page = self._group_images(images or [])

        if doc.exam_type == "shenlun":
            self._layout_shenlun(doc)
            return LaidOutDocument(pages=self._pages, total_pages=len(self._pages), config_snapshot=self.config.__dict__)

        questions_by_page: dict[int, list[Question]] = {}
        for question in doc.questions:
            questions_by_page.setdefault(question.source_page, []).append(question)
        self._page_questions = questions_by_page

        for question in doc.questions:
            self._layout_question(question)

        return LaidOutDocument(pages=self._pages, total_pages=len(self._pages), config_snapshot=self.config.__dict__)

    @property
    def content_top(self) -> float:
        return self.config.margin_top

    @property
    def content_bottom(self) -> float:
        return self.config.page_height_mm - self.config.margin_bottom

    @property
    def content_width(self) -> float:
        return max(20, self.config.page_width_mm - self.config.margin_left - self.config.margin_right)

    def _new_page(self):
        page = LaidOutPage(page_number=len(self._pages) + 1)
        self._pages.append(page)
        self._current_page = page
        self._current_y = self.config.margin_top

    def _add_page_number(self):
        if self.config.show_page_number and self._current_page:
            if any(elem.type == "page_number" for elem in self._current_page.elements):
                return
            self._current_page.elements.append(PageElement(
                type="page_number", text=f"- {self._current_page.page_number} -",
                x_mm=self.config.margin_left, y_mm=self.content_bottom + 5,
                font_name=self.config.page_num_font, font_size=self.config.page_num_size,
            ))

    def _ensure_space(self, needed_mm: float):
        needed_mm = max(0, needed_mm)
        if self._current_y + needed_mm > self.content_bottom and self._current_y > self.content_top:
            self._add_page_number()
            self._new_page()

    def _add_text_line(self, element_type: str, text: str, x_mm: float, font_name: str, font_size: float, line_height: float):
        self._ensure_space(line_height)
        self._current_page.elements.append(PageElement(
            type=element_type, text=text, x_mm=x_mm, y_mm=self._current_y,
            font_name=font_name, font_size=font_size, line_height_mm=line_height,
        ))
        self._current_y += line_height

    def _layout_question(self, question: Question):
        line_height = self._line_height(self.config.stem_size)
        if getattr(question, "section_heading", ""):
            self._layout_section_heading(question, line_height)

        q_label = f"{question.number}{self.config.question_suffix}"
        stem_segments = self._stem_segments(question.stem)
        stem_text = stem_segments[0] if stem_segments else ""

        prefix_w_mm = self._text_width_mm(q_label, self.config.stem_font, self.config.stem_size)
        first_line_width = max(10, self.content_width - prefix_w_mm - 2)
        stem_lines = self._break_lines(stem_text, first_line_width, self.config.stem_font, self.config.stem_size)
        first_body = stem_lines[0] if stem_lines else ""
        rest_text = stem_text[len(first_body):]
        self._add_text_line("question_number", q_label + first_body, self.config.margin_left, self.config.stem_font, self.config.stem_size, line_height)

        for line in self._break_lines(rest_text, self.content_width, self.config.stem_font, self.config.stem_size):
            if line:
                self._add_text_line("question_stem", line, self.config.margin_left, self.config.stem_font, self.config.stem_size, line_height)

        for segment in stem_segments[1:]:
            for line in self._break_lines(segment, self.content_width, self.config.stem_font, self.config.stem_size):
                if line:
                    self._add_text_line("question_stem", line, self.config.margin_left, self.config.stem_font, self.config.stem_size, line_height)

        self._place_images_for_question(question, self._page_questions.get(question.source_page, []))

        self._ensure_space(1)
        self._current_y += 1

        opt_indent = self.config.margin_left + self.config.option_indent_mm
        opt_width = max(10, self.content_width - self.config.option_indent_mm)
        opt_line_h = self._line_height(self.config.option_size)
        for opt in question.options:
            label = f"{opt.label}{self.config.option_suffix}"
            opt_text = label + self._normalize_option_text(opt.text)
            opt_lines = self._break_lines(opt_text, opt_width, self.config.option_font, self.config.option_size)
            current_indent = opt_indent
            for idx, line in enumerate(opt_lines):
                self._add_text_line("option_text", line, current_indent, self.config.option_font, self.config.option_size, opt_line_h)
                if idx == 0:
                    current_indent = opt_indent + self._text_width_mm(label, self.config.option_font, self.config.option_size)

        if self.config.show_answer_line:
            self._ensure_space(opt_line_h + 2)
            self._current_y += 2
            self._current_page.elements.append(PageElement(
                type="answer_line", text=" " * 40, x_mm=opt_indent, y_mm=self._current_y,
                font_name=self.config.option_font, font_size=self.config.option_size,
                width_mm=self.config.answer_line_length_mm,
            ))
            self._current_y += opt_line_h

        self._ensure_space(self.config.question_spacing_mm)
        self._current_y += self.config.question_spacing_mm

    def _layout_section_heading(self, question: Question, line_height: float):
        heading_lines = [line.strip() for line in str(getattr(question, "section_heading", "")).splitlines() if line.strip()]
        if getattr(question, "is_data_analysis", False) or self._is_data_analysis_section(heading_lines):
            self._layout_data_analysis_section(question, heading_lines, line_height)
            return
        self._add_compact_section_lines(heading_lines, line_height)
        self._ensure_space(1)
        self._current_y += 1
        self._place_images_for_section(question)

    def _layout_data_analysis_section(self, question: Question, heading_lines: list[str], line_height: float):
        images = self._take_images_for_section(question)
        pending_caption: list[str] = []
        pending_caption_page: int | None = None
        pending_caption_y: float | None = None
        pending_note: list[str] = []
        material_buffer: list[str] = []
        material_last_page: int | None = None
        material_last_y: float | None = None
        prompt_seen = False
        heading_xs = list(getattr(question, "section_line_xs", []) or [])
        heading_ys = list(getattr(question, "section_line_ys", []) or [])
        heading_pages = list(getattr(question, "section_line_pages", []) or [])
        fallback_page = getattr(question, "section_source_page", None) or question.source_page
        last_text_page = fallback_page
        events: list[dict] = []

        for idx, raw_line in enumerate(heading_lines):
            line = raw_line.strip()
            if not line:
                continue
            page_no = heading_pages[idx] if idx < len(heading_pages) and heading_pages[idx] else last_text_page
            last_text_page = page_no
            events.append({
                "type": "text",
                "page": page_no,
                "y": heading_ys[idx] if idx < len(heading_ys) else 0.0,
                "x": heading_xs[idx] if idx < len(heading_xs) else 0.0,
                "text": line,
            })

        for img in images:
            events.append({
                "type": "image",
                "page": img.page_number,
                "y": img.bbox[1],
                "x": img.bbox[0],
                "image": img,
            })

        events.sort(key=lambda item: (item["page"], item["y"], 1 if item["type"] == "image" else 0, item["x"]))
        material_xs = [item["x"] for item in events if item["type"] == "text" and self._is_material_paragraph_line(item["text"])]
        material_base_x = min(material_xs) if material_xs else 0.0

        def flush_material():
            nonlocal material_buffer, material_last_page, material_last_y
            if not material_buffer:
                return
            text = self._join_material_lines(material_buffer)
            if text:
                self._add_wrapped_material_line(
                    text,
                    0.0,
                    self.config.stem_font,
                    self.config.stem_size,
                    line_height,
                )
            material_buffer = []
            material_last_page = None
            material_last_y = None

        def flush_pending_caption():
            nonlocal pending_caption, pending_caption_page, pending_caption_y
            if pending_caption:
                self._add_compact_section_lines(pending_caption, line_height)
                pending_caption = []
            pending_caption_page = None
            pending_caption_y = None

        def flush_pending_note():
            nonlocal pending_note
            if pending_note:
                self._add_compact_section_lines(pending_note, line_height)
                pending_note = []

        def should_start_new_material_paragraph(page_no: int, y_mm: float, x_mm: float) -> bool:
            if not material_buffer:
                return False
            if self._is_new_material_paragraph_x(x_mm, material_base_x):
                return True
            return material_last_page == page_no and material_last_y is not None and y_mm - material_last_y > line_height * 1.7

        def next_image_after(page_no: int, y_mm: float) -> dict | None:
            for candidate in events:
                if candidate["type"] == "image" and candidate["page"] == page_no and candidate["y"] >= y_mm - 0.5:
                    return candidate
            return None

        def is_caption_continuation(event: dict) -> bool:
            if not pending_caption or pending_caption_page != event["page"] or pending_caption_y is None:
                return False
            if event["y"] - pending_caption_y > line_height * 1.5:
                return False
            image_event = next_image_after(event["page"], pending_caption_y)
            return bool(image_event and event["y"] <= image_event["y"] + 0.5)

        for event in events:
            if prompt_seen:
                continue
            if event["type"] == "image":
                flush_material()
                flush_pending_caption()
                self._add_image(event["image"])
                continue

            line = event["text"]
            if self._is_table_caption_line(line):
                flush_material()
                flush_pending_note()
                flush_pending_caption()
                pending_caption = [line]
                pending_caption_page = event["page"]
                pending_caption_y = event["y"]
                continue
            if is_caption_continuation(event) and not self._is_note_line(line) and not self._is_data_question_prompt(line):
                pending_caption.append(line)
                pending_caption_y = event["y"]
                continue
            if pending_caption:
                flush_pending_caption()
            if self._is_note_line(line):
                flush_material()
                flush_pending_caption()
                pending_note.append(line)
                continue
            if pending_note and not self._is_data_question_prompt(line):
                pending_note.append(line)
                continue
            if self._is_data_question_prompt(line):
                prompt_seen = True
                flush_material()
                flush_pending_caption()
                flush_pending_note()
                self._add_compact_section_lines([line], line_height)
                continue
            if pending_note:
                flush_pending_note()
            if self._is_material_paragraph_line(line):
                if should_start_new_material_paragraph(event["page"], event["y"], event["x"]):
                    flush_material()
                material_buffer.append(line)
                material_last_page = event["page"]
                material_last_y = event["y"]
            else:
                flush_material()
                self._add_compact_section_lines([line], line_height)

        flush_material()
        flush_pending_caption()
        flush_pending_note()
        self._ensure_space(1)
        self._current_y += 1

    def _add_compact_section_lines(self, lines: list[str], line_height: float):
        for text in lines:
            normalized = self._normalize_text(text)
            if not normalized:
                continue
            for line in self._break_lines(normalized, self.content_width, self.config.stem_font, self.config.stem_size):
                self._add_text_line("section_title", line, self.config.margin_left, self.config.stem_font, self.config.stem_size, line_height)

    def _estimate_caption_image_height(self, caption_lines: list[str], images: list[ImageBlock], line_height: float) -> float:
        total = 0.0
        for text in caption_lines:
            normalized = self._normalize_text(text)
            if normalized:
                total += len(self._break_lines(normalized, self.content_width, self.config.stem_font, self.config.stem_size)) * line_height
        for img in images:
            scale = min(
                self.content_width / max(img.width_mm, 1),
                (self.content_bottom - self.content_top) / max(img.height_mm, 1),
                1.0,
            )
            total += max(8, img.height_mm * scale) + 6
        return total

    def _layout_shenlun(self, doc: CleanedDocument):
        line_height = self._line_height(self.config.stem_size)
        self._add_section_title(GIVEN_MATERIAL)
        for material in doc.materials:
            text = self._normalize_text(material.text)
            if not text:
                continue
            element_type = "section_title" if material.is_section_title else "material"
            font = self.config.question_num_font if material.is_section_title else self.config.stem_font
            size = self.config.question_num_size if material.is_section_title else self.config.stem_size
            indent = 0.0 if material.is_section_title else self._two_chinese_chars_mm(font, size)
            width = max(20, self.content_width - indent)
            if material.is_section_title or indent <= 0:
                for line in self._break_lines(text, width, font, size):
                    self._add_text_line(element_type, line, self.config.margin_left + indent, font, size, line_height)
            else:
                self._add_wrapped_material_line(text, indent, font, size, line_height)
            spacing = self.config.paragraph_spacing_mm if material.is_section_title else 0.6
            self._ensure_space(spacing)
            self._current_y += spacing

        if doc.shenlun_questions:
            self._ensure_space(self.config.question_spacing_mm + line_height)
            self._current_y += self.config.question_spacing_mm
            self._add_section_title(ANSWER_REQUIREMENTS)
            for question in doc.shenlun_questions:
                self._ensure_shenlun_question_space(question)
                self._layout_shenlun_question(question)

    def _add_wrapped_material_line(self, text: str, indent: float, font: str, size: float, line_height: float):
        first_width = max(20, self.content_width - indent)
        first_lines = self._break_lines(text, first_width, font, size)
        first = first_lines[0] if first_lines else ""
        self._add_text_line("material", first, self.config.margin_left + indent, font, size, line_height)
        rest = text[len(first):]
        for line in self._break_lines(rest, self.content_width, font, size):
            if line:
                self._add_text_line("material", line, self.config.margin_left, font, size, line_height)

    def _two_chinese_chars_mm(self, font: str, size: float) -> float:
        width = self._text_width_mm(_u(0x6C49, 0x5B57), font, size)
        return width if width > 0 else size * 0.3528 * 2

    def _ensure_shenlun_question_space(self, question):
        needed = self._estimate_shenlun_question_height(question)
        usable = self.content_bottom - self.content_top
        self._ensure_space(min(needed, usable))

    def _estimate_shenlun_question_height(self, question) -> float:
        line_height = self._line_height(self.config.stem_size)
        opt_line_h = self._line_height(self.config.option_size)
        total = line_height
        content = self._normalize_question_text(question.content)
        total += len([line for line in self._break_lines(content, self.content_width, self.config.stem_font, self.config.stem_size) if line]) * line_height
        for req in question.requirements:
            total += self._estimate_instruction_height(self._normalize_question_text(req), opt_line_h)
        total += self.config.question_spacing_mm
        return total

    def _estimate_instruction_height(self, text: str, line_height: float) -> float:
        marker = re.match(r"^([\(\uff08]\s*[\u4e00-\u9fff\d]+\s*[\)\uff09])", text)
        if not marker:
            return len(self._break_lines(text, self.content_width, self.config.option_font, self.config.option_size)) * line_height
        label = marker.group(1)
        body = text[marker.end():]
        label_w = self._text_width_mm(label, self.config.option_font, self.config.option_size)
        first_width = max(10, self.content_width - label_w)
        first_lines = self._break_lines(body, first_width, self.config.option_font, self.config.option_size)
        first_body = first_lines[0] if first_lines else ""
        rest = body[len(first_body):]
        return (1 + len([line for line in self._break_lines(rest, max(10, self.content_width - label_w), self.config.option_font, self.config.option_size) if line])) * line_height

    def _add_section_title(self, title: str):
        line_height = self._line_height(self.config.question_num_size)
        self._add_text_line("section_title", title, self.config.margin_left, self.config.question_num_font, self.config.question_num_size, line_height)
        self._ensure_space(2)
        self._current_y += 2

    def _layout_shenlun_question(self, question):
        line_height = self._line_height(self.config.stem_size)
        label = getattr(question, "heading_label", "") or f"{question.number}."
        content = self._normalize_question_text(question.content)
        self._add_text_line("question_number", label, self.config.margin_left, self.config.stem_font, self.config.stem_size, line_height)
        for line in self._break_lines(content, self.content_width, self.config.stem_font, self.config.stem_size):
            if line:
                self._add_text_line("question_stem", line, self.config.margin_left, self.config.stem_font, self.config.stem_size, line_height)
        for req in question.requirements:
            self._add_wrapped_instruction(self._normalize_question_text(req))
        self._ensure_space(self.config.question_spacing_mm)
        self._current_y += self.config.question_spacing_mm

    def _add_wrapped_instruction(self, text: str):
        line_height = self._line_height(self.config.option_size)
        marker = re.match(r"^([\(\uff08]\s*[\u4e00-\u9fff\d]+\s*[\)\uff09])", text)
        if not marker:
            for line in self._break_lines(text, self.content_width, self.config.option_font, self.config.option_size):
                self._add_text_line("instruction", line, self.config.margin_left, self.config.option_font, self.config.option_size, line_height)
            return
        label = marker.group(1)
        body = text[marker.end():]
        label_w = self._text_width_mm(label, self.config.option_font, self.config.option_size)
        first_width = max(10, self.content_width - label_w)
        first_lines = self._break_lines(body, first_width, self.config.option_font, self.config.option_size)
        first_body = first_lines[0] if first_lines else ""
        self._add_text_line("instruction", label + first_body, self.config.margin_left, self.config.option_font, self.config.option_size, line_height)
        rest_text = body[len(first_body):]
        indent = self.config.margin_left + label_w
        rest_width = max(10, self.content_width - label_w)
        for line in self._break_lines(rest_text, rest_width, self.config.option_font, self.config.option_size):
            if line:
                self._add_text_line("instruction", line, indent, self.config.option_font, self.config.option_size, line_height)

    def _group_images(self, images: list[ImageBlock]) -> dict[int, list[ImageBlock]]:
        grouped: dict[int, list[ImageBlock]] = {}
        for img in images:
            grouped.setdefault(img.page_number, []).append(img)
        for page_images in grouped.values():
            page_images.sort(key=lambda i: (i.bbox[1], i.bbox[0]))
        return grouped

    def _place_images_for_question(self, question: Question, page_questions: list[Question]):
        for img in self._take_images_in_source_range(
            start_page=question.source_page,
            start_y=getattr(question, "source_y_mm", 0) or 0,
            end_page=getattr(question, "source_end_page", None) or question.source_page,
            end_y=getattr(question, "source_end_y_mm", None),
        ):
            self._add_image(img)

    def _place_images_for_section(self, question: Question):
        for img in self._take_images_for_section(question):
            self._add_image(img)

    def _take_images_for_section(self, question: Question) -> list[ImageBlock]:
        if not getattr(question, "section_heading", ""):
            return []
        start_page = getattr(question, "section_source_page", None)
        if start_page is None:
            return []
        return self._take_images_in_source_range(
            start_page=start_page,
            start_y=getattr(question, "section_source_y_mm", 0) or 0,
            end_page=getattr(question, "section_end_page", None) or question.source_page,
            end_y=getattr(question, "section_end_y_mm", None),
        )

    def _take_images_in_source_range(self, start_page: int, start_y: float, end_page: int, end_y: float | None) -> list[ImageBlock]:
        assigned_by_page: dict[int, list[ImageBlock]] = {}
        for page_no in range(start_page, end_page + 1):
            page_images = self._images_by_page.get(page_no, [])
            if not page_images:
                continue
            assigned: list[ImageBlock] = []
            for img in page_images:
                img_y = img.bbox[1]
                if page_no == start_page and img_y + 2 < start_y:
                    continue
                if page_no == end_page and end_y is not None and img_y >= end_y - 2:
                    continue
                assigned.append(img)
            if assigned:
                assigned_by_page[page_no] = assigned

        result: list[ImageBlock] = []
        for page_no in sorted(assigned_by_page):
            assigned = assigned_by_page[page_no]
            result.extend(assigned)
            page_images = self._images_by_page.get(page_no, [])
            self._images_by_page[page_no] = [img for img in page_images if img not in assigned]
        return result

    def _add_image(self, img: ImageBlock):
        scale = min(
            self.content_width / max(img.width_mm, 1),
            (self.content_bottom - self.content_top) / max(img.height_mm, 1),
            1.0,
        )
        w = max(10, img.width_mm * scale)
        h = max(8, img.height_mm * scale)
        self._ensure_space(h + 4)
        x = self.config.margin_left + max(0, (self.content_width - w) / 2)
        self._current_page.elements.append(PageElement(
            type="image", text="", x_mm=x, y_mm=self._current_y + 2,
            font_name="SimSun", font_size=10, image_data=img.image_bytes,
            image_w_mm=w, image_h_mm=h,
        ))
        self._current_y += h + 6

    def _line_height(self, font_size: float) -> float:
        multiplier = max(0.8, self.config.line_height_multiplier)
        return max(font_size * 0.3528 * multiplier, font_size * 0.3528 + 0.8)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return "".join(LayoutEngine._sanitize_text(text).split())

    @staticmethod
    def _normalize_question_text(text: str) -> str:
        text = LayoutEngine._sanitize_text(text)
        if LayoutEngine._looks_like_formula(text):
            return re.sub(r"[ \t]+", " ", text.replace("\r", "").replace("\n", "").strip())
        return "".join(text.split())

    @staticmethod
    def _normalize_option_text(text: str) -> str:
        text = LayoutEngine._sanitize_text(text)
        if LayoutEngine._looks_like_formula(text):
            return re.sub(r"[ \t]+", " ", text.replace("\r", "").replace("\n", "").strip())
        placeholder = "\uE000"
        text = text.replace("\r", "").replace("\n", "")
        text = re.sub(r"[ \t]{2,}", placeholder, text.strip())
        text = "".join(text.split())
        return text.replace(placeholder, "  ")

    @staticmethod
    def _sanitize_text(text: str) -> str:
        text = str(text or "")
        text = text.translate({
            0x00A0: 0x20, 0x2000: 0x20, 0x2001: 0x20, 0x2002: 0x20,
            0x2003: 0x20, 0x2004: 0x20, 0x2005: 0x20, 0x2006: 0x20,
            0x2007: 0x20, 0x2008: 0x20, 0x2009: 0x20, 0x200A: 0x20,
            0x202F: 0x20, 0x205F: 0x20, 0x3000: 0x20,
        })
        cleaned = []
        for ch in text:
            code = ord(ch)
            if code in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0xFFFC):
                continue
            if 0xE000 <= code <= 0xF8FF:
                continue
            if code < 32 and ch not in "\r\n\t":
                continue
            cleaned.append(ch)
        return "".join(cleaned)

    @staticmethod
    def _looks_like_formula(text: str) -> bool:
        text = LayoutEngine._sanitize_text(text)
        operator = r"[=+\-*/×÷≤≥<>≈∶√^]"
        if re.search(rf"(?:\d|[A-Za-z])\s*{operator}\s*(?:\d|[A-Za-z])", text):
            return True
        if re.search(r"\d+\s*/\s*\d+", text):
            return True
        return False
        if re.search(r"[=＋+×xX*/÷≤≥<>≈∶:_%％√∑^]", text or ""):
            return True
        return bool(re.search(r"\d\s+[+\-*/×÷=]\s*\d", text or ""))

    @staticmethod
    def _stem_segments(text: str) -> list[str]:
        normalized = LayoutEngine._normalize_question_text(text)
        if not normalized:
            return [""]
        circled = "".join(chr(c) for c in (0x2460, 0x2461, 0x2462, 0x2463, 0x2464, 0x2465, 0x2466, 0x2467, 0x2468, 0x2469))
        matches = list(re.finditer(f"[{re.escape(circled)}]", normalized))
        if not matches:
            return [normalized]
        segments: list[str] = []
        first_start = matches[0].start()
        if first_start > 0:
            segments.append(normalized[:first_start])
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
            segments.append(normalized[match.start():end])
        return segments or [normalized]

    @staticmethod
    def _is_data_analysis_section(lines: list[str]) -> bool:
        compact = "".join("".join(line.split()) for line in lines)
        return DATA_ANALYSIS in compact or "璧勬枡鍒嗘瀽" in compact

    @staticmethod
    def _is_table_caption_line(line: str) -> bool:
        compact = "".join((line or "").split())
        return bool(re.match(rf"^[{TABLE_CHAR}{FIGURE_CHAR}]\d*[：:]?.*", compact))

    @staticmethod
    def _is_note_line(line: str) -> bool:
        compact = "".join((line or "").split())
        return compact.startswith(NOTE_CHAR) or compact.startswith("注:") or compact.startswith("注：")

    @staticmethod
    def _is_data_question_prompt(line: str) -> bool:
        compact = "".join((line or "").split())
        return compact.startswith(QUESTION_PROMPT_PREFIX)

    @staticmethod
    def _is_material_paragraph_line(line: str) -> bool:
        compact = "".join((line or "").split())
        if not compact:
            return False
        if LayoutEngine._is_table_caption_line(compact) or LayoutEngine._is_note_line(compact) or LayoutEngine._is_data_question_prompt(compact):
            return False
        if DATA_ANALYSIS in compact or re.match(r"^\u7b2c.*\u90e8\u5206", compact):
            return False
        if re.match(r"^[\uff08\(]?\s*\u5171\s*\d+\s*\u9898", compact) or "\u53c2\u8003\u65f6\u95f4" in compact:
            return False
        if re.match(r"^[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u3001\.\uff0e]", compact):
            return False
        return bool(len(compact) >= 10 and re.search(r"[\u4e00-\u9fff]", compact))

    @staticmethod
    def _join_material_lines(lines: list[str]) -> str:
        return "".join("".join(LayoutEngine._sanitize_text(line).split()) for line in lines)

    @staticmethod
    def _is_new_material_paragraph_x(line_x: float, base_x: float) -> bool:
        if line_x <= 0 or base_x <= 0:
            return False
        return line_x - base_x >= 4.0

    @staticmethod
    def _text_width_mm(text: str, font_name: str, font_size: float) -> float:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        return stringWidth(text, font_name, font_size) * 25.4 / 72

    def _break_lines(self, text: str, max_width_mm: float, font_name: str, font_size: float) -> list[str]:
        text = text or ""
        if not text.strip():
            return [""]
        from reportlab.pdfbase.pdfmetrics import stringWidth
        max_w_pt = max(max_width_mm, 5) * 72 / 25.4
        lines, cur = [], ""
        for ch in text:
            if stringWidth(cur + ch, font_name, font_size) <= max_w_pt or not cur:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        return lines or [text]

    def finish(self):
        if self._current_page and self._current_page.elements:
            self._add_page_number()
