"""速算题本 — 排版样式原型脚本（开发用，极简版）。

每道题只含三要素：给出数 → 求什么量 → 计算方式。
页面结构：封面 → 题目页（分模块） → 答案速查表 → 解法速查表。

运行: python tools/quick_math/dev/make_sample.py
输出: sample_quick_math.pdf（项目根目录）
"""

import sys
from pathlib import Path

# 确保可以从项目根目录导入 tools 包（脚本在 tools/quick_math/dev/ 下运行）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from tools.pdf_converter.core.generator.font_manager import FontManager

OUT_PATH = Path(__file__).resolve().parents[3] / "sample_quick_math.pdf"

INDIGO = colors.HexColor("#4F46E5")
INDIGO_SOFT = colors.HexColor("#EEF2FF")
DARK = colors.HexColor("#1F2937")
GRAY = colors.HexColor("#9CA3AF")
LINE = colors.HexColor("#E5E7EB")

# ──────────────────────────── 题目数据 ────────────────────────────
# 每题: (模块, 题干, 选项, 答案, 计算方式一行)
QUESTIONS = [
    # ── 模块一 基础运算 ──
    ("模块一  基础运算", "3247 + 5689 = ?",
     ["8936", "8931", "8946", "8926"], "A", "尾数法：7+9=16，个位为 6"),
    ("模块一  基础运算", "1/8 = ?%",
     ["12.5%", "11.1%", "14.3%", "16.7%"], "A", "特殊分数：1/8 = 12.5%"),
    ("模块一  基础运算", "4567 ÷ 998 ≈ ?",
     ["4.58", "4.34", "4.72", "4.91"], "A", "凑整：÷1000=4.567，分母略小 → 4.58"),
    ("模块一  基础运算", "8561 − 4789 = ?",
     ["3772", "3782", "3762", "3792"], "A", "尾数法：11−9=2，个位为 2"),

    # ── 模块二 ABRX 四要素 ──
    ("模块二  ABRX 四要素", "现期 8872，同比 −22.9% → 求基期",
     ["11510", "6839", "8872", "9412"], "A", "截位直除：8872 ÷ 0.771 ≈ 11510"),
    ("模块二  ABRX 四要素", "现期 12000，增长量 2000 → 求基期",
     ["9800", "10000", "14000", "10200"], "B", "基期 = 现期 − 增量 = 10000"),
    ("模块二  ABRX 四要素", "现期 48810，同比 +4.6% → 求增长量",
     ["1950", "2150", "2240", "2440"], "B", "415份数法：48810÷104.6≈466.6，×4.6≈2150"),
    ("模块二  ABRX 四要素", "基期 4000，增长率 +25% → 求增长量",
     ["800", "1000", "1200", "500"], "B", "增量 = 基期 × 率 = 1000"),
    ("模块二  ABRX 四要素", "现期 12000，基期 10000 → 求增长率",
     ["20%", "25%", "16.7%", "22.2%"], "A", "R = 2000 ÷ 10000 = 20%"),
    ("模块二  ABRX 四要素", "现期 5000，增长量 1000 → 求增长率",
     ["20%", "25%", "16.7%", "33.3%"], "B", "R = 1000 ÷ 4000 = 25%"),
    ("模块二  ABRX 四要素", "基期 5460，增长率 +14% → 求现期",
     ["6120", "6224", "5980", "6350"], "B", "现期 = 5460 × 1.14 ≈ 6224"),
    ("模块二  ABRX 四要素", "基期 8000，增长量 900 → 求现期",
     ["7100", "8900", "8800", "9050"], "B", "现期 = 基期 + 增量 = 8900"),

    # ── 模块三 速算方法专项 ──
    ("模块三  速算方法专项", "56789 ÷ 234567 ≈ ?",
     ["22.1%", "24.2%", "26.3%", "28.4%"], "B", "截位直除（截3位）：568 ÷ 2346 ≈ 24.2%"),
    ("模块三  速算方法专项", "现期 12000，增长率 +25% → 求增长量",
     ["2000", "2400", "3000", "3600"], "B", "415：125:25 = 5:1，12000 ÷ 5 = 2400"),
    ("模块三  速算方法专项", "3/7、4/9、5/11、2/5 中最大的是",
     ["3/7", "4/9", "5/11", "2/5"], "C", "化小数：0.455 最大"),
    ("模块三  速算方法专项", "甲 10000→12000，乙 6500→8000 → 增速更高的是",
     ["甲市", "乙市", "一样高", "无法比较"], "B", "乙：1500÷6500≈23.1% > 甲 20%"),

    # ── 模块四 高频考点 ──
    ("模块四  高频考点", "部分 51.2，整体 159.4 → 求比重",
     ["28.6%", "32.1%", "35.4%", "24.8%"], "B", "51.2 ÷ 159.4 ≈ 32.1%"),
    ("模块四  高频考点", "部分增速 +2.5%，整体增速 +1.1% → 比重变化",
     ["上升", "下降", "不变", "无法判断"], "A", "部分率 > 整体率 → 上升"),
    ("模块四  高频考点", "总量 +1.8%，份数 +0.5% → 平均数增长率",
     ["1.3%", "1.8%", "0.8%", "2.3%"], "A", "(1.8%−0.5%) ÷ 1.005 ≈ 1.3%"),
    ("模块四  高频考点", "A 是 B 的 3 倍 → A 比 B 多几倍",
     ["3 倍", "2 倍", "4 倍", "1.5 倍"], "B", "多几倍 = 是几倍 − 1 = 2 倍"),
    ("模块四  高频考点", "初期 8000，末期 10648，间隔 3 年 → 年均增速",
     ["8%", "10%", "12%", "15%"], "B", "10648÷8000=1.331=1.1³ → 10%"),

    # ── 模块五 综合训练 ──
    ("模块五  综合训练", "甲 12000(+20%)，乙 8000(+14.3%)，丙 6500(+8.3%)，丁 5000(−10%) → 增长量最大",
     ["甲市", "乙市", "丙市", "丁市"], "A", "415：甲 2000，乙≈1000，丙≈500，丁为负"),
    ("模块五  综合训练", "乙市 8000，同比 +14.3% → 求基期",
     ["6800", "7000", "7200", "6400"], "B", "14.3%≈1/7：8000 × 7/8 = 7000"),
    ("模块五  综合训练", "能推出的是",
     ["2022 年 GDP 最高的是甲市", "丁市 2023 年同比上升",
      "四市合计超过 32000 亿元", "乙市增速低于丙市"], "A",
     "甲基期 10000 最高；合计 31500 < 32000；丁下降；乙 > 丙"),
]

ANSWER_KEY = [("1", "A"), ("2", "A"), ("3", "A"), ("4", "A"), ("5", "A"), ("6", "B"),
              ("7", "B"), ("8", "B"), ("9", "A"), ("10", "B"), ("11", "B"), ("12", "B"),
              ("13", "B"), ("14", "B"), ("15", "C"), ("16", "B"), ("17", "B"), ("18", "A"),
              ("19", "A"), ("20", "B"), ("21", "B"), ("22", "A"), ("23", "B"), ("24", "A")]

# ──────────────────────────── 排版 ────────────────────────────


class NumberedCanvas(canvas.Canvas):
    """自动统计总页数的画布（实现“第 X 页 / 共 Y 页”）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(total)
            super().showPage()
        super().save()

    def draw_page_number(self, total):
        self.setFont("SimSun", 8)
        self.setFillColor(GRAY)
        self.drawCentredString(A4[0] / 2, 10 * mm, f"第 {self._pageNumber} 页 / 共 {total} 页")


def build_styles(fm: FontManager) -> dict:
    sun = fm.get_fallback("SimSun")
    hei = fm.get_fallback("SimHei")
    styles = {}
    styles["cover_title"] = ParagraphStyle(
        "cover_title", fontName=hei, fontSize=26, leading=36,
        textColor=INDIGO, alignment=1)
    styles["cover_sub"] = ParagraphStyle(
        "cover_sub", fontName=sun, fontSize=10.5, leading=16,
        textColor=GRAY, alignment=1)
    styles["section"] = ParagraphStyle(
        "section", fontName=hei, fontSize=11, leading=15,
        textColor=colors.white, alignment=1)
    styles["question"] = ParagraphStyle(
        "question", fontName=sun, fontSize=10.5, leading=15,
        textColor=DARK)
    styles["option"] = ParagraphStyle(
        "option", fontName=sun, fontSize=10, leading=13.5,
        textColor=DARK, leftIndent=6)
    styles["page_title"] = ParagraphStyle(
        "page_title", fontName=hei, fontSize=15, leading=21, textColor=DARK)
    styles["key_cell"] = ParagraphStyle(
        "key_cell", fontName=sun, fontSize=10, leading=14,
        textColor=DARK, alignment=1)
    styles["key_ans"] = ParagraphStyle(
        "key_ans", fontName=hei, fontSize=10, leading=14,
        textColor=INDIGO, alignment=1)
    styles["solution_no"] = ParagraphStyle(
        "solution_no", fontName=sun, fontSize=9.5, leading=13.5,
        textColor=DARK, alignment=1)
    styles["solution_ans"] = ParagraphStyle(
        "solution_ans", fontName=hei, fontSize=9.5, leading=13.5,
        textColor=INDIGO, alignment=1)
    styles["solution_text"] = ParagraphStyle(
        "solution_text", fontName=sun, fontSize=9.5, leading=13.5,
        textColor=DARK)
    return styles


def build_story(st: dict) -> list:
    story = []

    # ── 封面页（极简） ──
    story.append(Spacer(1, 50 * mm))
    story.append(Paragraph("资料分析速算题本", st["cover_title"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("难度：基础·进阶 ｜ 共 24 题 ｜ 样式预览版（原型数据）", st["cover_sub"]))
    story.append(PageBreak())

    # ── 题目页 ──
    current_module = None
    for no, (module, text, options, answer, method) in enumerate(QUESTIONS, 1):
        if module != current_module:
            current_module = module
            bar = Table([[Paragraph(module, st["section"])]], colWidths=[176 * mm])
            bar.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), INDIGO),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            block = [bar, Spacer(1, 2 * mm),
                     Paragraph(f"{no}.  {text}", st["question"]),
                     option_table(options, st),
                     Spacer(1, 2.5 * mm)]
            story.append(KeepTogether(block))
            continue

        story.append(Paragraph(f"{no}.  {text}", st["question"]))
        story.append(option_table(options, st))
        story.append(Spacer(1, 2.5 * mm))

    story.append(PageBreak())

    # ── 答案速查表 ──
    story.append(Paragraph("答案速查表", st["page_title"]))
    story.append(Spacer(1, 3 * mm))
    key_rows = []
    for i in range(0, len(ANSWER_KEY), 6):
        row = []
        for no, ans in ANSWER_KEY[i:i + 6]:
            row.append(Paragraph(no, st["key_cell"]))
            row.append(Paragraph(ans, st["key_ans"]))
        while len(row) < 12:
            row.append(Paragraph("", st["key_cell"]))
        key_rows.append(row)
    key_table = Table(key_rows, colWidths=[11 * mm] * 12)
    key_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(key_table)
    story.append(PageBreak())

    # ── 解法速查表（题号 / 答案 / 计算方式） ──
    story.append(Paragraph("解法速查表", st["page_title"]))
    story.append(Spacer(1, 3 * mm))
    sol_rows = [[Paragraph("题号", st["key_ans"]),
                 Paragraph("答案", st["key_ans"]),
                 Paragraph("计算方式", st["key_ans"])]]
    for no, (module, text, options, answer, method) in enumerate(QUESTIONS, 1):
        sol_rows.append([Paragraph(str(no), st["solution_no"]),
                         Paragraph(answer, st["solution_ans"]),
                         Paragraph(method, st["solution_text"])])
    sol_table = Table(sol_rows, colWidths=[14 * mm, 14 * mm, 148 * mm])
    sol_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INDIGO_SOFT),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sol_table)

    return story


def option_table(options: list, st: dict) -> Table:
    """两行两列的选项表格（每行 2 个选项）。"""
    letters = ["A", "B", "C", "D"]
    cells = [[Paragraph(f"<font color='#4F46E5'><b>{letters[r * 2 + c]}.</b></font>  {options[r * 2 + c]}",
                        st["option"]) for c in range(2)]
             for r in range(2)]
    table = Table(cells, colWidths=[88 * mm, 88 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def main():
    fm = FontManager()
    fm.register_all()
    st = build_styles(fm)
    story = build_story(st)

    doc = SimpleDocTemplate(
        str(OUT_PATH),
        pagesize=A4,
        topMargin=18 * mm, bottomMargin=16 * mm,
        leftMargin=17 * mm, rightMargin=17 * mm,
        title="资料分析速算题本（样式预览）",
        author="公考小工具",
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"样例 PDF 已生成: {OUT_PATH}")


if __name__ == "__main__":
    main()
