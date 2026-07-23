"""数据模型: 定义PDF转换流水线中各阶段的数据结构。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextBlock:
    """PDF中的一个文本块(带位置和样式信息)。"""
    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) in mm, origin top-left
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    is_bold: bool = False
    page_number: int = 0

    def __repr__(self) -> str:
        return f"TextBlock(text={self.text[:30]!r}, font={self.font_name}, size={self.font_size})"


@dataclass
class ImageBlock:
    """PDF中的图片块。"""
    image_bytes: bytes
    image_ext: str = "png"
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)  # mm
    page_number: int = 0
    width_mm: float = 0
    height_mm: float = 0
    orig_page_h_mm: float = 297  # 原始页面高度，用于坐标缩放


@dataclass
class ParsedPage:
    """解析后的单个页面。"""
    blocks: list[TextBlock] = field(default_factory=list)
    images: list[ImageBlock] = field(default_factory=list)
    page_number: int = 0
    width_mm: float = 210.0
    height_mm: float = 297.0


@dataclass
class ParsedDocument:
    """解析后的完整PDF文档。"""
    pages: list[ParsedPage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    source_type: str = "text"  # "text" | "image" | "mixed"


@dataclass
class Option:
    """一道选择题的选项。"""
    label: str        # "A", "B", "C", "D"
    text: str         # 选项内容文本


@dataclass
class Question:
    """一道题目(行测选择题)。"""
    number: int
    stem: str                               # 题干文本
    options: list[Option] = field(default_factory=list)
    answer: Optional[str] = None            # 参考答案
    source_page: int = 0


@dataclass
class MaterialBlock:
    """申论给定资料的一个段落块。"""
    text: str
    paragraph_index: int = 0
    is_section_title: bool = False
    indent_mm: float = 0.0


@dataclass
class ShenlunQuestion:
    """申论作答要求中的一道题。"""
    number: int
    content: str                            # 题目内容
    score: Optional[str] = None             # 分值，如 "(20分)"
    requirements: list[str] = field(default_factory=list)  # 要求条目
    heading_label: str = ""                 # 原文题号，如 "第一题" 或 "1."


@dataclass
class CleanedDocument:
    """清洗后的文档——结构化题目列表。"""
    exam_type: str = "xingce"               # "xingce" | "shenlun"
    questions: list[Question] = field(default_factory=list)
    materials: list[MaterialBlock] = field(default_factory=list)
    shenlun_questions: list[ShenlunQuestion] = field(default_factory=list)
    filtered_out: list[str] = field(default_factory=list)  # 被过滤掉的内容
    ignored_pages: list[int] = field(default_factory=list)  # 整页跳过，如申论作答纸
    answer_section_lines: list[str] = field(default_factory=list)  # 答案对照表文本（已废弃，用 answer_sections）
    answer_sections: list = field(default_factory=list)  # [(after_question_number, [text_lines]), ...] 答案段落，按原位插入


@dataclass
class PageElement:
    """排版后的页面元素——带有精确坐标的绘图指令。"""
    type: str       # "header" | "question_number" | "question_stem" |
                    # "option_label" | "option_text" | "answer_line" |
                    # "page_number" | "material" | "section_title" |
                    # "instruction" | "shenlun_question" | "grid_line" |
                    # "image"
    text: str = ""
    x_mm: float = 0
    y_mm: float = 0
    font_name: str = "SimSun"
    font_size: float = 10.5
    is_bold: bool = False
    width_mm: float = 0.0
    line_height_mm: float = 0.0
    image_data: bytes | None = None  # 图片二进制数据(type="image"时)
    image_w_mm: float = 0            # 图片宽度
    image_h_mm: float = 0            # 图片高度


@dataclass
class LaidOutPage:
    """排版后的一页。"""
    elements: list[PageElement] = field(default_factory=list)
    page_number: int = 0


@dataclass
class LaidOutDocument:
    """排版后的完整文档——可直接送入PDF生成器。"""
    pages: list[LaidOutPage] = field(default_factory=list)
    total_pages: int = 0
    config_snapshot: dict = field(default_factory=dict)
