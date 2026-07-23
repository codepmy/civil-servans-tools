"""转换流水线编排器: 串联 解析→清洗→排版→生成 全流程。"""

import io
from typing import Callable

from tools.pdf_converter.core.models import ParsedDocument, CleanedDocument, LaidOutDocument
from tools.pdf_converter.core.parser.text_parser import TextParser
from tools.pdf_converter.core.cleaner.xingce_cleaner import XingceCleaner, detect_exam_type
from tools.pdf_converter.core.cleaner.shenlun_cleaner import ShenlunCleaner
from tools.pdf_converter.core.layout.engine import LayoutEngine, LayoutConfig
from tools.pdf_converter.core.generator.font_manager import FontManager
from tools.pdf_converter.core.generator.pdf_generator import PDFGenerator
from tools.pdf_converter.config.settings import load_template


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

        if not cleaned.questions and not cleaned.shenlun_questions and not cleaned.materials:
            if parsed.source_type == "image":
                if progress:
                    progress(45, "OCR结构化失败，切换扫描件保真模式...")
                return self._generate_image_preserved_pdf(input_path, exam_type, overrides, progress)
            raise ValueError(
                "未能从PDF中提取到任何题目。\n"
                "可能原因：\n"
                "1. PDF为扫描版/图片型，OCR引擎未能识别文字\n"
                "2. PDF内容不是公务员考试题目格式\n"
                "请确认PDF清晰度，或检查题目格式是否正确。"
            )

        if parsed.source_type == "image" and self._ocr_structure_is_poor(parsed, cleaned):
            if progress:
                progress(45, "OCR结构不稳定，切换扫描件保真模式...")
            return self._generate_image_preserved_pdf(input_path, exam_type, overrides, progress)

        if progress:
            progress(50, "计算排版...")
        # 收集所有图片
        ignored_pages = set(cleaned.ignored_pages)
        all_images = []
        for pg in parsed.pages:
            if pg.page_number in ignored_pages:
                continue
            all_images.extend(pg.images)
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
        """解析PDF文件 — 文字型走 PyMuPDF，扫描型走 PaddleOCR。"""
        pdf_type = TextParser.detect_pdf_type(path)
        if pdf_type == "image":
            try:
                from tools.pdf_converter.core.parser.ocr_parser import OCRParser
            except (ImportError, RuntimeError) as exc:
                raise self._ocr_dependency_error(exc) from exc

            if OCRParser.is_first_time():
                if progress:
                    progress(5, "首次使用OCR，正在下载模型（约100MB）...")
            else:
                if progress:
                    progress(5, "检测到扫描版PDF，加载OCR引擎...")

            parser = OCRParser()
        else:
            parser = TextParser()

        try:
            return parser.parse(path, progress)
        except RuntimeError as exc:
            error_text = str(exc)
            if "当前环境未安装 OCR 依赖" in error_text or "当前 PaddlePaddle 不是可用的 CUDA 版本" in error_text:
                raise self._ocr_dependency_error(exc) from exc
            raise

    @staticmethod
    def _ocr_dependency_error(exc: Exception) -> RuntimeError:
        return RuntimeError(
            "该PDF为扫描版/图片型，需要使用 OCR 引擎识别文字。\n"
            "当前环境未安装 OCR 依赖（PaddleOCR/PaddlePaddle），请运行 setup.bat 安装。\n"
            "安装完成后，setup.bat 末尾显示 GPU 可用: True 才表示 GPU 可用。\n\n"
            f"原始错误: {exc}"
        )

    def _clean(self, doc: ParsedDocument, exam_type: str,
               progress: Callable[[int, str], None] = None) -> CleanedDocument:
        """清洗文档内容。"""
        if exam_type == "shenlun":
            cleaner = ShenlunCleaner()
        else:
            cleaner = XingceCleaner()
        return cleaner.clean(doc, progress)

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
    def _ocr_structure_is_poor(parsed: ParsedDocument, cleaned: CleanedDocument) -> bool:
        """Return True when OCR text extraction is too unreliable to reflow safely."""
        page_count = max(1, len(parsed.pages))

        if cleaned.exam_type != "xingce":
            return False

        question_count = len(cleaned.questions)
        if question_count == 0:
            return True

        # Xingce papers normally contain multiple choice questions densely
        # across pages.  For long-format sections (言语/资料分析) each page
        # may hold only 1–2 questions, so we require at least ¼ of the page
        # count before trusting the OCR for reflow.
        if page_count >= 8 and question_count < max(5, page_count // 4):
            return True

        option_counts = [len(q.options) for q in cleaned.questions]
        abnormal_options = sum(1 for count in option_counts if count < 3 or count > 5)
        abnormal_ratio = abnormal_options / max(1, question_count)
        if question_count >= 8 and abnormal_ratio >= 0.45:
            return True

        empty_ocr_pages = sum(1 for page in parsed.pages if not page.blocks)
        if page_count >= 5 and empty_ocr_pages / page_count >= 0.2 and question_count < page_count * 1.5:
            return True

        return False

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

    def _generate_image_preserved_pdf(self, input_path: str, exam_type: str,
                                      overrides: dict | None = None,
                                      progress: Callable[[int, str], None] = None) -> bytes:
        """Render each source page as an image and center it on the target paper."""
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

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_w_mm * mm, page_h_mm * mm))

        with fitz.open(input_path) as src:
            total = max(1, src.page_count)
            for index, page in enumerate(src, start=1):
                if progress:
                    pct = 45 + int(index / total * 45)
                    progress(pct, f"扫描件保真渲染... {index}/{total}")

                pix = page.get_pixmap(dpi=200, alpha=False)
                img_bytes = pix.tobytes("png")
                src_w_mm = page.rect.width * 25.4 / 72
                src_h_mm = page.rect.height * 25.4 / 72
                scale = min(
                    content_w_mm / max(src_w_mm, 1.0),
                    content_h_mm / max(src_h_mm, 1.0),
                )
                draw_w_mm = src_w_mm * scale
                draw_h_mm = src_h_mm * scale
                x_mm = config.margin_left + (content_w_mm - draw_w_mm) / 2
                y_top_mm = config.margin_top + (content_h_mm - draw_h_mm) / 2

                reader = ImageReader(io.BytesIO(img_bytes))
                c.drawImage(
                    reader,
                    x_mm * mm,
                    (page_h_mm - y_top_mm - draw_h_mm) * mm,
                    width=draw_w_mm * mm,
                    height=draw_h_mm * mm,
                    preserveAspectRatio=True,
                    anchor="c",
                )
                c.showPage()

        c.save()
        output = buf.getvalue()

        if progress:
            progress(100, "完成!（扫描件保真模式）")

        return output

    def get_available_fonts(self) -> list[str]:
        """获取可用字体列表(供UI使用)。"""
        return self._font_manager.available_fonts()

    def get_template_names(self) -> list[str]:
        """获取可用模板列表。"""
        return ["xingce", "shenlun"]
