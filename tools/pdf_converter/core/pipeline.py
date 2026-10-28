"""转换流水线编排器: 串联 解析→清洗→排版→生成 全流程。"""

import re
from typing import Callable

from tools.pdf_converter.core.models import ParsedDocument, CleanedDocument, LaidOutDocument
from tools.pdf_converter.core.parser.text_parser import TextParser
from tools.pdf_converter.core.cleaner.xingce_cleaner import XingceCleaner, detect_exam_type
from tools.pdf_converter.core.cleaner.shenlun_cleaner import ShenlunCleaner
from tools.pdf_converter.core.layout.engine import LayoutEngine, LayoutConfig
from tools.pdf_converter.core.generator.font_manager import FontManager
from tools.pdf_converter.core.generator.pdf_generator import PDFGenerator
from tools.pdf_converter.config.settings import load_template


SCANNED_PDF_MESSAGE = (
    "该PDF为扫描件（图片型），暂不支持转换。\n"
    "请使用刷题App导出的文字版PDF。"
)


class ScannedPdfError(ValueError):
    """扫描件/图片型 PDF 无法转换为可重排的真题格式。"""

    def __init__(self, message: str = SCANNED_PDF_MESSAGE):
        super().__init__(message)


# ============================================================
# 行测模块删除（"删除所选模块"）
# ============================================================
# 模块名 → 可能的写法（顺序有意义: 长名在前, 避免"言语理解"抢先匹配
# "言语理解与表达" 后把"与表达"当成正文）
XINGCE_MODULE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("政治理论", ("政治理论",)),
    ("常识判断", ("常识判断",)),
    ("言语理解与表达", ("言语理解与表达", "言语理解")),
    ("数量关系", ("数量关系",)),
    ("判断推理", ("判断推理",)),
    ("资料分析", ("资料分析",)),
)

# 模块标题行的前导序号: "一." / "（二）" / "第一部分" / "模块三"
_ORDINAL_PREFIX_RE = re.compile(
    r"^(?:第\s*[一二三四五六七八九十百零]+\s*部分"
    r"|模块\s*[一二三四五六七八九十百零]+"
    r"|[（(]?[一二三四五六七八九十百零]+[)）.、．,，:：])"
)

_CN_DIGITS = "一二三四五六七八九十"


def to_chinese_number(n: int) -> str:
    """1 → 一, 12 → 十二, 21 → 二十一（只用于模块标题重编号）。"""
    if n <= 0:
        return ""
    if n <= 10:
        return _CN_DIGITS[n - 1]
    if n < 20:
        return "十" + _CN_DIGITS[n - 11]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _CN_DIGITS[tens - 1] + "十" + (_CN_DIGITS[ones - 1] if ones else "")
    return str(n)


def _starts_with_module(body: str) -> bool:
    return any(body.startswith(alias) for _, aliases in XINGCE_MODULE_ALIASES for alias in aliases)


def modules_in_heading(text: str) -> set[str]:
    """从一行（或一段）标题文本里解析出模块名。

    只认"标题形态"的模块名: 模块名后面必须紧跟结尾、冒号、括号、
    "共N题"、分隔符或另一个模块名。这样材料正文里的
    "资料分析表明…" / "数量关系是…" 不会被误判成模块标题。
    支持合并式标题: "政治理论/常识判断"、"政治理论+常识判断"。
    """
    found: set[str] = set()
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        body = _ORDINAL_PREFIX_RE.sub("", line, count=1).strip()
        # 一个标题最多连着写 3 个模块名（合并式标题）
        for _ in range(3):
            matched = False
            for key, aliases in XINGCE_MODULE_ALIASES:
                for alias in aliases:
                    if not body.startswith(alias):
                        continue
                    rest = body[len(alias):]
                    if (rest == "" or rest[0] in "：:（(【[—－-+＋/、，,　 "
                            or rest.startswith("共") or _starts_with_module(rest)):
                        found.add(key)
                        body = rest.lstrip("：:（(【[—－-+＋/、，,　 ")
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                break
    return found


def _rewrite_ordinal(line: str, new_cn: str) -> str:
    """把标题行的前导序号换成 new_cn（"六. 资料分析" → "三. 资料分析"）。"""
    m = _ORDINAL_PREFIX_RE.match(line)
    if not m:
        return line
    prefix = m.group(0)
    new_prefix = re.sub(r"[一二三四五六七八九十百零]+", new_cn, prefix, count=1)
    return new_prefix + line[m.end():]


class ConversionPipeline:
    """PDF格式转换流水线。

    用法:
        pipeline = ConversionPipeline()
        output_pdf_bytes = pipeline.run("input.pdf", progress_callback)
    """

    def __init__(self):
        self._font_manager = FontManager()
        self._font_manager.register_all()

    def run(self, input_path: str,
            progress: Callable[[int, str], None] = None,
            template_name: str = "xingce",
            config_overrides: dict | None = None) -> bytes:
        """执行完整的转换流水线。

        Args:
            input_path: 输入PDF路径
            progress: 进度回调 (percent, stage_name)
            template_name: 模板名称 ("xingce" 或 "shenlun")
            config_overrides: UI设置覆盖，如 {'body_font':'FangSong', 'body_size':14.0, 'page_size':'B5', ...}

        Returns:
            输出PDF的二进制数据
        """
        overrides = config_overrides or {}

        if progress:
            progress(0, "解析PDF...")
        parsed = self._parse(input_path, progress)

        if progress:
            progress(20, "检测题型...")
        exam_type = template_name if template_name in ("xingce", "shenlun") \
            else detect_exam_type(parsed)

        if progress:
            progress(30, "清洗内容...")
        cleaned = self._clean(parsed, exam_type, progress)

        # 「行测-删除所选模块」: 必须在空题目检查之前完成 —— 删完可能一题不剩
        drop_sections = overrides.get("drop_sections") or []
        excluded_ranges = self._filter_sections(
            cleaned, drop_sections, exam_type, progress,
            renumber_questions=bool(overrides.get("renumber_questions", False)),
        )

        if not cleaned.questions and not cleaned.shenlun_questions and not cleaned.materials:
            raise ValueError(
                "未能从PDF中提取到任何题目。\n"
                "可能原因：\n"
                "1. PDF内容不是公务员考试题目格式\n"
                "2. PDF文字层缺失或排版过于复杂\n"
                "请检查PDF内容是否为刷题App导出的文字版试卷。"
            )

        if progress:
            progress(50, "计算排版...")
        # 收集所有图片
        ignored_pages = set(cleaned.ignored_pages)
        all_images = []
        for pg in parsed.pages:
            if pg.page_number in ignored_pages:
                continue
            all_images.extend(pg.images)
        if excluded_ranges:
            # 被删模块的图表/表格图不能留给上一题: 按源坐标区间剔除
            all_images = [
                img for img in all_images
                if not self._image_in_ranges(img, excluded_ranges)
            ]
        laid_out = self._layout(cleaned, exam_type, progress, overrides, all_images)

        if progress:
            progress(70, "生成PDF...")
        output = self._generate(laid_out, progress)

        if overrides.get("keep_last_page"):
            output = self._append_last_page(input_path, output, exam_type, overrides)

        if progress:
            progress(100, "完成!")

        return output

    def _parse(self, path: str,
               progress: Callable[[int, str], None] = None) -> ParsedDocument:
        """解析PDF文件 — 仅支持文字型 PDF，扫描件直接拒绝。"""
        if TextParser.detect_pdf_type(path) == "image":
            raise ScannedPdfError()

        return TextParser().parse(path, progress)

    def _clean(self, doc: ParsedDocument, exam_type: str,
               progress: Callable[[int, str], None] = None) -> CleanedDocument:
        """清洗文档内容。"""
        if exam_type == "shenlun":
            cleaner = ShenlunCleaner()
        else:
            cleaner = XingceCleaner()
        return cleaner.clean(doc, progress)

    def _filter_sections(self, doc: CleanedDocument, drop_sections: list[str],
                         exam_type: str,
                         progress: Callable[[int, str], None] = None,
                         renumber_questions: bool = False) -> list[tuple]:
        """删除所选行测模块，并递补模块序号与答案区位置。

        题号默认保持原卷编号；renumber_questions=True 时从 1 连续重排。

        返回被删内容在源 PDF 上的坐标区间 [(起页, 起y, 止页, 止y), ...]，
        供上层把落在区间里的图片（资料分析表格、图形推理选项图）一并剔除 ——
        否则它们会被前一道保留的题"抢走"。
        """
        if exam_type != "xingce" or not drop_sections:
            return []
        drop = {str(name).strip() for name in drop_sections if str(name).strip()}
        if not drop:
            return []

        questions = list(doc.questions)
        if not questions:
            return []

        keep_flags: list[bool] = []
        excluded: list[tuple] = []
        current_modules: set[str] = set()
        title_lines: list[str] = []      # 被删首题标题里不含模块名的卷面标题行
        for idx, question in enumerate(questions):
            heading = str(getattr(question, "section_heading", "") or "")
            mods = modules_in_heading(heading)
            if mods:
                current_modules = mods
            keep = not (current_modules & drop)
            keep_flags.append(keep)
            if keep:
                continue
            # 源区间此刻仍是"删除前"的注解, 各题区间首尾相接
            start_page = getattr(question, "section_source_page", None) or question.source_page
            start_y = getattr(question, "section_source_y_mm", None)
            if start_y is None:
                start_y = getattr(question, "source_y_mm", 0.0) or 0.0
            excluded.append((
                start_page, start_y,
                getattr(question, "source_end_page", None),
                getattr(question, "source_end_y_mm", None),
            ))
            # 首题标题里排在模块标题之前的行是卷面标题（如"2026年…《行测》题"），
            # 不属于模块内容，转挂到后面第一个保留的题上，免得整卷标题凭空消失
            if idx == 0 and heading:
                for line in heading.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if modules_in_heading(stripped):
                        break
                    title_lines.append(stripped)

        if all(keep_flags):
            doc.filtered_out.append(
                "[section-filter] 未识别到所选模块对应的小节标题，本次未删除任何内容"
            )
            return []
        if not any(keep_flags):
            raise ValueError(
                "删除所选模块后没有剩余题目。\n"
                "请至少保留一个模块再转换。"
            )

        kept = [q for q, keep in zip(questions, keep_flags) if keep]

        # ── 答案区位置重映射: after_count 是"第几题之后", 删题后按保留题数重算
        remapped = [
            (sum(1 for keep in keep_flags[:max(0, int(after_count))] if keep), lines)
            for after_count, lines in getattr(doc, "answer_sections", []) or []
        ]
        doc.answer_sections = remapped

        # ── 题号处理: 默认保持原卷编号（便于按原题号对答案/回看），
        #    用户勾选"从 1 连续递补"时才重排
        if renumber_questions:
            for new_number, question in enumerate(kept, start=1):
                question.number = new_number

        # ── 模块序号递补（"五. 判断推理" → "四. 判断推理"）+ 资料分析标记重算
        has_module_heading = any(
            modules_in_heading(getattr(q, "section_heading", "")) for q in kept
        )
        ordinal = 0
        current_modules = set()
        for question in kept:
            heading = str(getattr(question, "section_heading", "") or "")
            mods = modules_in_heading(heading)
            if mods:
                ordinal += 1
                current_modules = mods
                new_cn = to_chinese_number(ordinal)
                question.section_heading = "\n".join(
                    _rewrite_ordinal(line, new_cn) if modules_in_heading(line) else line
                    for line in heading.splitlines()
                )
            if has_module_heading:
                # 资料分析走专门的图表排版分支; 上一个模块被删后必须按新归属重算
                question.is_data_analysis = "资料分析" in current_modules

        if title_lines and kept:
            first = kept[0]
            existing = str(getattr(first, "section_heading", "") or "")
            first.section_heading = "\n".join(
                title_lines + ([existing] if existing else [])
            )

        # ── 题目源区间重连: 图片归属按"保留后的相邻题"重新计算
        XingceCleaner._annotate_question_ranges(kept)

        doc.questions = kept
        doc.filtered_out.append(
            "[section-filter] 已删除模块: " + "、".join(sorted(drop))
            + f"（剩余 {len(kept)} 题）"
        )
        if progress:
            progress(45, f"已删除所选模块，剩余 {len(kept)} 题")
        return excluded

    @staticmethod
    def _image_in_ranges(img, ranges: list[tuple]) -> bool:
        """图片的源坐标是否落在被删除的区间里。"""
        page = getattr(img, "page_number", 0)
        y = img.bbox[1] if getattr(img, "bbox", None) else 0.0
        for start_page, start_y, end_page, end_y in ranges:
            if page < start_page:
                continue
            if end_page is not None and page > end_page:
                continue
            if page == start_page and y < (start_y or 0.0) - 2:
                continue
            if end_page is not None and page == end_page and end_y is not None and y >= end_y - 2:
                continue
            return True
        return False

    def _layout(self, doc: CleanedDocument, exam_type: str,
                progress: Callable[[int, str], None] = None,
                overrides: dict | None = None,
                images: list | None = None) -> LaidOutDocument:
        """排版文档。"""
        template = load_template(exam_type)
        config = LayoutConfig.from_template(template, overrides or {})

        engine = LayoutEngine(config)
        result = engine.layout(doc, images=images)
        engine.finish()

        if progress:
            progress(65, f"排版完成: {result.total_pages} 页")

        return result

    def _generate(self, doc: LaidOutDocument,
                  progress: Callable[[int, str], None] = None) -> bytes:
        """生成最终PDF。"""
        generator = PDFGenerator(self._font_manager)
        output = generator.generate(doc)

        if progress:
            progress(95, "输出完成")

        return output

    @staticmethod
    def _append_last_page(input_path: str, output: bytes, exam_type: str,
                          overrides: dict | None = None) -> bytes:
        """将源 PDF 最后一页以图片形式追加到输出 PDF 末尾。

        用于"保留尾页（对答案二维码）"功能：源 PDF 最后一页通常包含
        二维码和广告文字，以原样截图方式保留，不做文字重排。
        """
        import io
        import fitz
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        template = load_template(exam_type)
        config = LayoutConfig.from_template(template, overrides or {})
        page_w_mm = config.page_width_mm
        page_h_mm = config.page_height_mm
        content_w_mm = max(20.0, page_w_mm - config.margin_left - config.margin_right)
        content_h_mm = max(20.0, page_h_mm - config.margin_top - config.margin_bottom)

        with fitz.open(input_path) as src:
            if src.page_count < 1:
                return output
            last_page = src[-1]
            pix = last_page.get_pixmap(dpi=200, alpha=False)
            img_bytes = pix.tobytes("png")
            src_w_mm = last_page.rect.width * 25.4 / 72
            src_h_mm = last_page.rect.height * 25.4 / 72

        scale = min(
            content_w_mm / max(src_w_mm, 1.0),
            content_h_mm / max(src_h_mm, 1.0),
        )
        draw_w_mm = src_w_mm * scale
        draw_h_mm = src_h_mm * scale
        x_mm = config.margin_left + (content_w_mm - draw_w_mm) / 2
        y_top_mm = config.margin_top + (content_h_mm - draw_h_mm) / 2

        # 用 PyMuPDF 将最后一页追加到已有输出 PDF
        out_doc = fitz.open(stream=output, filetype="pdf")
        # 创建单页 PDF 包含源最后一页的截图
        tail_buf = io.BytesIO()
        c = canvas.Canvas(tail_buf, pagesize=(page_w_mm * mm, page_h_mm * mm))
        reader = ImageReader(io.BytesIO(img_bytes))
        c.drawImage(
            reader,
            x_mm * mm,
            (page_h_mm - y_top_mm - draw_h_mm) * mm,
            width=draw_w_mm * mm,
            height=draw_h_mm * mm,
            preserveAspectRatio=True,
        )
        c.save()
        tail_bytes = tail_buf.getvalue()

        # 将截图页插入到输出文档末尾
        tail_doc = fitz.open(stream=tail_bytes, filetype="pdf")
        out_doc.insert_pdf(tail_doc)
        result = out_doc.tobytes()
        out_doc.close()
        tail_doc.close()
        return result

    def get_available_fonts(self) -> list[str]:
        """获取可用字体列表(供UI使用)。"""
        return self._font_manager.available_fonts()

    def get_template_names(self) -> list[str]:
        """获取可用模板列表。"""
        return ["xingce", "shenlun"]
