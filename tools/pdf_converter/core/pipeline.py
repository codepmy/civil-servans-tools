"""转换流水线编排器: 串联 解析→清洗→排版→生成 全流程。"""

from pathlib import Path
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
            raise ValueError(
                "未能从PDF中提取到任何题目。\n"
                "请确认PDF内容为公务员考试题目格式。"
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
        laid_out = self._layout(cleaned, exam_type, progress, overrides, all_images)

        if progress:
            progress(70, "生成PDF...")
        output = self._generate(laid_out, progress)

        if progress:
            progress(100, "完成!")

        return output

    def _parse(self, path: str,
               progress: Callable[[int, str], None] = None) -> ParsedDocument:
        """解析PDF文件。"""
        parser = TextParser()
        return parser.parse(path, progress)

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

    def get_available_fonts(self) -> list[str]:
        """获取可用字体列表(供UI使用)。"""
        return self._font_manager.available_fonts()

    def get_template_names(self) -> list[str]:
        """获取可用模板列表。"""
        return ["xingce", "shenlun"]
