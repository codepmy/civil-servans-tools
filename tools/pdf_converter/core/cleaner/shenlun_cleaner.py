"""申论内容清洗器: 提取给定资料和作答要求。"""

import re
import unicodedata
from typing import Callable

from tools.pdf_converter.core.models import ParsedDocument, CleanedDocument, MaterialBlock, ShenlunQuestion


class ShenlunCleaner:
    """申论内容清洗器。"""

    MATERIAL_SECTION_RE = re.compile(r"^(?:给定(?:资料|材料)|材料)\s*\d*\s*[：:]?$")
    MATERIAL_NUM_RE = re.compile(r"^\s*(\d+)\s*[\.．、。]\s*(.+)$")
    QUESTION_SECTION_RE = re.compile(r"^(?:作答要求|作答任务|答题要求|问题|题目)")
    QUESTION_HEADING_RE = re.compile(r"^第\s*([一二三四五六七八九十百两0-9\d]+)\s*(?:大)?题[：:]?\s*(.*)$")
    QUESTION_HEADING_SCAN_RE = re.compile(r"第\s*[一二三四五六七八九十百两0-9\d]+\s*题")
    QUESTION_NUM_RE = re.compile(r"^\s*(\d+)\s*[\.．、。]\s*(.*)$")
    ANSWER_SHEET_RE = re.compile(r"^(?:答题纸|作答纸|答题卡|作答区|第[一二三四五六七八九十百两0-9\d]+大题|\d+字)$")
    REQUIREMENT_RE = re.compile(r"^(?:要求|注意事项|作答要求)\s*[：:]")
    SUB_REQUIREMENT_RE = re.compile(r"(?:^|(?<![\d\w]))[（(]\s*([一二三四五六七八九十百两0-9\d]+)\s*[)）]")

    def clean(self, doc: ParsedDocument,
              progress: Callable[[int, str], None] = None) -> CleanedDocument:
        """清洗申论文档。"""
        filtered_out: list[str] = []
        material_lines: list[dict] = []
        question_lines: list[str] = []
        ignored_pages: list[int] = []
        section = "notice"
        seen_answer_sheet = False

        for i, page in enumerate(doc.pages):
            if progress:
                progress(int((i + 1) / len(doc.pages) * 100), "申论清洗")

            content_blocks, removed = self._filter_blocks(page)
            filtered_out.extend(removed)
            if not content_blocks:
                if seen_answer_sheet:
                    ignored_pages.append(page.page_number)
                    filtered_out.append(f"[作答纸页] 第{page.page_number}页")
                continue

            page_lines = self._lines_from_blocks(content_blocks)
            page_text = "\n".join(item["text"] for item in page_lines)
            if self._is_answer_sheet_page(page_text) or (
                seen_answer_sheet and self._is_answer_sheet_continuation(page_text)
            ):
                ignored_pages.append(page.page_number)
                filtered_out.append(f"[作答纸页] 第{page.page_number}页")
                seen_answer_sheet = True
                section = "answer_sheet"
                continue
            page_lines = self._ordered_page_lines_for_section(page_lines, section)

            for item in page_lines:
                raw_text = item["text"]
                line = self._normalize_line(raw_text)
                if not line:
                    continue
                line = self._strip_embedded_noise(line)
                if not line:
                    filtered_out.append(f"[页眉页脚] {raw_text[:50]}")
                    continue
                if self._is_empty_quote_line(line):
                    filtered_out.append(f"[空引号] {line[:50]}")
                    continue
                if self._is_noise_line(line):
                    filtered_out.append(f"[页眉页脚] {line[:50]}")
                    continue
                if line == "注意事项":
                    section = "notice"
                    continue
                if section == "notice" and not self.MATERIAL_SECTION_RE.match(line):
                    filtered_out.append(f"[注意事项] {line[:50]}")
                    continue
                section_prefix = self.QUESTION_SECTION_RE.match(line)
                if section_prefix:
                    section = "question"
                    remainder = line[section_prefix.end():].strip()
                    if remainder:
                        question_lines.append(self._question_line_item(item, remainder))
                    continue
                if self.ANSWER_SHEET_RE.match(line):
                    if page.page_number not in ignored_pages:
                        ignored_pages.append(page.page_number)
                        filtered_out.append(f"[作答纸页] 第{page.page_number}页")
                    seen_answer_sheet = True
                    section = "answer_sheet"
                    continue
                if section == "answer_sheet":
                    continue
                if self.MATERIAL_SECTION_RE.match(line):
                    section = "material"
                    material_lines.append({"text": line, "indent": 0.0, "title": True})
                    continue
                if section == "material":
                    material_lines.append({
                        "text": line,
                        "indent": item.get("indent", 0.0),
                        "title": bool(self.MATERIAL_NUM_RE.match(line)),
                    })
                    continue
                if section == "question":
                    question_lines.append(self._question_line_item(item, line))

        all_materials = self._clean_materials(material_lines)
        all_questions = self._clean_questions(question_lines)
        ignored_pages = sorted(set(ignored_pages))

        return CleanedDocument(
            exam_type="shenlun",
            materials=all_materials,
            shenlun_questions=all_questions,
            filtered_out=filtered_out,
            ignored_pages=ignored_pages,
        )

    def _filter_blocks(self, page) -> tuple[list, list]:
        """过滤非内容块。"""
        content = []
        removed = []

        for block in page.blocks:
            text = self._normalize_line(block.text)
            if not text:
                continue

            fs = block.font_size or 10

            if self._is_likely_ad(
                text, fs, block.bbox[0], block.bbox[1],
                page.height_mm, page.width_mm,
            ):
                removed.append(f"[广告] {text}")
                continue

            if re.match(r"^[\d\-/]+$", text) and fs < 8:
                removed.append(f"[页码] {text}")
                continue

            content.append(block)

        return content, removed

    @classmethod
    def _lines_from_blocks(cls, blocks: list) -> list[dict]:
        if not blocks:
            return []
        ordered = cls._fix_inline_order(blocks)
        groups: list[list] = []
        for block in ordered:
            y = block.bbox[1]
            placed = False
            for group in groups:
                group_y = sum(item.bbox[1] for item in group) / len(group)
                if abs(y - group_y) <= 3.2:
                    group.append(block)
                    placed = True
                    break
            if not placed:
                groups.append([block])
        lines = []
        for group in groups:
            group = sorted(group, key=lambda b: b.bbox[0])
            text = "".join(block.text for block in group).strip()
            if not text:
                continue
            lines.append({
                "text": text,
                "x": group[0].bbox[0],
                "page": group[0].page_number,
                "indent": max(0.0, min(group[0].bbox[0] - 20.0, 18.0)),
                "y": sum(block.bbox[1] for block in group) / len(group),
            })
        return lines

    @classmethod
    def _ordered_page_lines_for_section(cls, lines: list[dict], section: str) -> list[dict]:
        return lines

    @classmethod
    def _question_line_item(cls, item: dict, text: str) -> dict:
        return {
            "text": text,
            "page": int(item.get("page", 0) or 0),
            "y": float(item.get("y", 0.0) or 0.0),
            "x": float(item.get("x", 0.0) or 0.0),
        }

    @classmethod
    def _question_reading_order(cls, lines: list[dict]) -> list[dict]:
        """作答要求页可能是左右两栏，按栏阅读避免右栏题目跑到左栏顶部。"""
        if len(lines) < 4:
            return lines
        xs = sorted({round(float(item.get("x", 0.0)), 1) for item in lines})
        if len(xs) < 2 or xs[-1] - xs[0] < 45.0:
            return lines
        gaps = [(xs[idx + 1] - xs[idx], idx) for idx in range(len(xs) - 1)]
        gap, idx = max(gaps)
        if gap < 25.0:
            return lines
        split_x = (xs[idx] + xs[idx + 1]) / 2
        left = [item for item in lines if float(item.get("x", 0.0)) <= split_x]
        right = [item for item in lines if float(item.get("x", 0.0)) > split_x]
        if len(left) < 2 or len(right) < 2:
            return lines
        left_has_question = any(cls.QUESTION_HEADING_RE.match(cls._normalize_line(item.get("text", ""))) for item in left)
        right_has_question = any(cls.QUESTION_HEADING_RE.match(cls._normalize_line(item.get("text", ""))) for item in right)
        if not (left_has_question and right_has_question):
            return lines
        return sorted(left, key=lambda item: item.get("y", 0.0)) + sorted(right, key=lambda item: item.get("y", 0.0))

    @classmethod
    def _clean_materials(cls, material_lines: list[dict]) -> list[MaterialBlock]:
        materials: list[MaterialBlock] = []
        current_parts: list[str] = []
        current_indent = 0.0

        def flush_current() -> None:
            nonlocal current_parts, current_indent
            text = "".join(current_parts).strip()
            if text:
                materials.append(MaterialBlock(
                    text=text,
                    paragraph_index=len(materials),
                    is_section_title=False,
                    indent_mm=current_indent,
                ))
            current_parts = []
            current_indent = 0.0

        for item in material_lines:
            text = (item.get("text") or "").strip()
            if not text:
                continue
            is_title = bool(item.get("title"))
            indent = 0.0 if is_title else float(item.get("indent", 0.0))
            if is_title:
                flush_current()
                materials.append(MaterialBlock(
                    text=text,
                    paragraph_index=len(materials),
                    is_section_title=True,
                    indent_mm=0.0,
                ))
                continue
            starts_paragraph = indent >= 1.5
            if starts_paragraph or not current_parts:
                flush_current()
                current_indent = indent
            current_parts.append(text)
        flush_current()
        return materials

    @classmethod
    def _clean_questions(cls, question_lines: list[str]) -> list[ShenlunQuestion]:
        questions: list[ShenlunQuestion] = []
        current: ShenlunQuestion | None = None
        collecting_requirements = False
        ordered_lines = cls._ordered_question_texts(question_lines)
        normalized_lines = cls._expand_question_heading_lines(ordered_lines)
        for raw in normalized_lines:
            line = cls._strip_embedded_noise(cls._normalize_line(raw))
            if not line or cls._is_noise_line(line):
                continue
            heading_match = cls.QUESTION_HEADING_RE.match(line)
            num_match = cls.QUESTION_NUM_RE.match(line)
            if heading_match:
                label = line[:heading_match.start(2)].strip() if heading_match.group(2) else line.strip()
                current = cls._make_question(
                    cls._parse_number(heading_match.group(1)),
                    heading_match.group(2),
                    heading_label=label,
                )
                questions.append(current)
                collecting_requirements = bool(current.requirements)
                continue
            if current is not None and num_match:
                current = cls._make_question(
                    int(num_match.group(1)), num_match.group(2), heading_label=f"{num_match.group(1)}.",
                )
                questions.append(current)
                collecting_requirements = bool(current.requirements)
                continue
            if current is None:
                continue
            if cls.REQUIREMENT_RE.match(line) or line.startswith(("（", "(", "要求")):
                collecting_requirements = True
            if collecting_requirements:
                current.requirements.append(line)
            else:
                content, requirements = cls._split_inline_requirements(cls._clean_question_content(line))
                current.content = cls._join_text(current.content, content)
                if requirements:
                    collecting_requirements = True
                    current.requirements.extend(requirements)
        cleaned: list[ShenlunQuestion] = []
        for question in questions:
            question.content = question.content.strip()
            question.requirements = cls._normalize_requirements(question.requirements)
            if not question.content and not question.requirements:
                continue
            cleaned.append(question)
        cleaned.sort(key=lambda question: question.number if question.number > 0 else 9999)
        return cleaned

    @classmethod
    def _ordered_question_texts(cls, question_lines: list) -> list[str]:
        items = []
        for idx, item in enumerate(question_lines):
            if isinstance(item, dict):
                text = item.get("text", "")
                page = int(item.get("page", 0) or 0)
                y = float(item.get("y", 0.0) or 0.0)
                x = float(item.get("x", 0.0) or 0.0)
            else:
                text = str(item)
                page = 0
                y = float(idx)
                x = 0.0
            items.append((page, y, x, idx, text))
        items.sort(key=lambda row: row[:4])
        return [text for *_meta, text in items]

    @classmethod
    def _expand_question_heading_lines(cls, lines: list[str]) -> list[str]:
        expanded: list[str] = []
        for line in lines:
            line = cls._normalize_line(line)
            parts = cls._split_question_heading_line(line)
            expanded.extend(parts if parts else [line])
        return expanded

    @staticmethod
    def _fix_inline_order(blocks: list) -> list:
        if len(blocks) < 2:
            return blocks
        sorted_blocks = sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0]))
        lines: list[list] = []
        for block in sorted_blocks:
            y = block.bbox[1]
            placed = False
            for line in lines:
                line_y = sum(item.bbox[1] for item in line) / len(line)
                if abs(y - line_y) <= 3.2:
                    line.append(block)
                    placed = True
                    break
            if not placed:
                lines.append([block])
        ordered = []
        for line in lines:
            ordered.extend(sorted(line, key=lambda b: b.bbox[0]))
        return ordered

    def _merge_blocks(self, blocks: list) -> str:
        """合并文本块。申论通常是段落文本，保留段落分隔。"""
        if not blocks:
            return ""

        sorted_blocks = self._fix_inline_order(blocks)

        lines = []
        current_line = ""
        last_y = None

        line_height = 7
        if len(sorted_blocks) >= 2:
            dys = [abs(sorted_blocks[i].bbox[1] - sorted_blocks[i - 1].bbox[1])
                   for i in range(1, min(len(sorted_blocks), 10))]
            if dys:
                line_height = sorted(dys)[len(dys) // 2]
        line_gap_threshold = max(2.5, min(line_height * 0.7, 5.0))

        for block in sorted_blocks:
            y = block.bbox[1]

            if last_y is not None and abs(y - last_y) > line_gap_threshold:
                if current_line.strip():
                    lines.append(current_line.strip())
                current_line = block.text
                last_y = y
                continue

            current_line += block.text
            last_y = y

        if current_line.strip():
            lines.append(current_line.strip())

        return "\n".join(lines)

    @staticmethod
    def _normalize_line(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text or "")
        normalized = normalized.translate(str.maketrans({
            "⼀": "一", "⼆": "二", "⼪": "三", "⼤": "大", "⻓": "长",
        }))
        return "".join(normalized.split())

    @staticmethod
    def _is_empty_quote_line(line: str) -> bool:
        return bool(re.fullmatch(r"[\"'“”‘’`·.。:：,，、\s]+", line or ""))

    @staticmethod
    def _join_text(prefix: str, text: str) -> str:
        return f"{prefix}{text}" if prefix else text

    @classmethod
    def _make_question(cls, number: int, raw_content: str, heading_label: str = "") -> ShenlunQuestion:
        content, requirements = cls._split_inline_requirements(cls._clean_question_content(raw_content))
        question = ShenlunQuestion(
            number=number,
            content=content,
            requirements=requirements,
            heading_label=cls._normalize_question_label(heading_label, number),
        )
        return question

    @staticmethod
    def _normalize_question_label(label: str, number: int) -> str:
        label = (label or "").strip()
        if label:
            label = re.sub(r"[：:]$", "", label).strip()
            return label
        return f"第{number}题"

    @staticmethod
    def _strip_embedded_noise(line: str) -> str:
        line = (line or "").strip()
        line = re.sub(r"[·•]?本试卷由.*?第\d+页,?共\d+页.*$", "", line)
        line = re.sub(r"[·•]?第\d+页,?共\d+页.*$", "", line)
        return line.strip()

    @staticmethod
    def _split_inline_requirements(text: str) -> tuple[str, list[str]]:
        text = (text or "").strip()
        match = re.search(r"(要求|注意事项|作答要求)\s*[：:]", text)
        if not match:
            return text, []
        content = text[:match.start()].strip()
        requirement = text[match.start():].strip()
        return content, [requirement] if requirement else []

    @classmethod
    def _normalize_requirements(cls, requirements: list[str]) -> list[str]:
        result: list[str] = []
        for req in requirements:
            text = (req or "").strip()
            if not text:
                continue
            parts = cls._split_sub_requirements(text)
            result.extend(part for part in parts if part.strip())
        return result

    @classmethod
    def _split_sub_requirements(cls, text: str) -> list[str]:
        text = (text or "").strip()
        matches = list(cls.SUB_REQUIREMENT_RE.finditer(text))
        if len(matches) <= 1:
            return [text] if text else []
        parts: list[str] = []
        prefix = text[:matches[0].start()].strip()
        if prefix:
            parts.append(prefix)
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            part = text[match.start():end].strip()
            if part:
                parts.append(part)
        return parts

    @staticmethod
    def _clean_question_content(text: str) -> str:
        text = (text or "").strip()
        text = ShenlunCleaner._strip_embedded_noise(text)
        return text.strip()

    @classmethod
    def _is_answer_sheet_page(cls, page_text: str) -> bool:
        lines = [cls._normalize_line(line) for line in (page_text or "").split("\n")]
        lines = [cls._strip_embedded_noise(line) for line in lines if line.strip()]
        lines = [line for line in lines if line and not cls._is_noise_line(line)]
        if not lines:
            return False
        joined = "".join(lines)
        answer_markers = sum(1 for line in lines if cls.ANSWER_SHEET_RE.match(line))
        answer_markers += len(re.findall(r"第[一二三四五六七八九十百两0-9\d]{1,3}大题", joined))
        grid_markers = len(re.findall(r"\d{1,4}字", joined))
        has_answer_title = any(marker in joined for marker in ("答题纸", "作答纸", "答题卡", "作答区"))
        has_question_content = any(
            cls.QUESTION_HEADING_RE.match(line) or cls._looks_like_question_line(line)
            for line in lines
        )
        if has_question_content:
            return False
        return has_answer_title or answer_markers >= 2 or grid_markers >= 2

    @classmethod
    def _is_answer_sheet_continuation(cls, page_text: str) -> bool:
        lines = [cls._normalize_line(line) for line in (page_text or "").split("\n") if line.strip()]
        lines = [cls._strip_embedded_noise(line) for line in lines]
        lines = [line for line in lines if line and not cls._is_noise_line(line)]
        if not lines:
            return True
        joined = "".join(lines)
        grid_markers = len(re.findall(r"\d{1,4}字", joined))
        answer_markers = len(re.findall(r"第[一二三四五六七八九十百两0-9\d]{1,3}大题", joined))
        has_question_content = any(
            cls.QUESTION_HEADING_RE.match(line) or cls._looks_like_question_line(line)
            for line in lines
        )
        return not has_question_content and (grid_markers >= 1 or answer_markers >= 1)

    @classmethod
    def _split_question_heading_line(cls, line: str) -> list[str]:
        matches = list(cls.QUESTION_HEADING_SCAN_RE.finditer(line))
        if len(matches) <= 1:
            return []
        parts = []
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
            parts.append(line[match.start():end])
        return parts

    @staticmethod
    def _parse_number(value: str) -> int:
        if value.isdigit():
            return int(value)
        digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        if value in digits:
            return digits[value]
        if value.startswith("十"):
            return 10 + digits.get(value[1:], 0)
        if "十" in value:
            left, right = value.split("十", 1)
            return digits.get(left, 1) * 10 + digits.get(right, 0)
        return 0

    @staticmethod
    def _looks_like_question_line(line: str) -> bool:
        cues = ("请", "谈谈", "概括", "归纳", "分析", "提出", "拟写", "写一篇", "联系实际")
        score_or_limit = "分)" in line or "分）" in line or "不超过" in line or "不少于" in line or "字" in line
        return any(cue in line for cue in cues) and score_or_limit

    @staticmethod
    def _is_noise_line(line: str) -> bool:
        if not line:
            return True
        if "本试卷由" in line:
            return True
        if re.fullmatch(r"[·•]?第\d+页,?共\d+页.*", line):
            return True
        if re.fullmatch(r"\d{4}年.*《申论》题(?:\([^)]*\)|（[^）]*）)?", line):
            return True
        return False

    @staticmethod
    def _is_likely_ad(text: str, font_size: float, x_mm: float, y_mm: float,
                      page_height_mm: float, page_width_mm: float) -> bool:
        keywords = ("关注", "公众号", "扫码", "二维码", "微信", "QQ", "客服", "报名", "粉笔")
        is_corner = (x_mm < 20 or x_mm > page_width_mm - 40) and (y_mm < 20 or y_mm > page_height_mm - 20)
        return any(keyword in text for keyword in keywords) and (is_corner or font_size < 9)
