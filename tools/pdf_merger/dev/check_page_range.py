"""验证"页数范围 -> 右侧预览"的联动。

用法:
    python tools/pdf_merger/dev/check_page_range.py [pdf]

检查项:
  1. 默认(未改范围)预览覆盖全文
  2. 改起始/结束页后, 预览范围跟着变, 当前页落进范围内
  3. 翻页不越出选定范围
  4. 切换选中文件时, 预览使用该文件自己的范围
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

import fitz
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from tools.pdf_merger.ui.widget import FileItemWidget, PdfMergerWidget

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  [通过] {message}")
    else:
        print(f"  [失败] {message}")
        FAILURES.append(message)


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841
    pdf = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "行测套卷.pdf")
    if not os.path.exists(pdf):
        print(f"找不到测试文件: {pdf}")
        raise SystemExit(1)

    with fitz.open(pdf) as doc:
        total = doc.page_count
    print(f"测试文件: {os.path.basename(pdf)}  共 {total} 页\n")

    window = PdfMergerWidget()
    window._add_paths([pdf])
    item = window.list_widget.item(0)
    row = item.data(Qt.ItemDataRole.UserRole + 1)
    assert isinstance(row, FileItemWidget)

    window.list_widget.setCurrentRow(0)
    preview = window.preview

    print("1) 默认范围 = 全文")
    check(preview._range == (1, total), f"范围 {preview._range} == (1, {total})")
    check("拼合" not in preview.label_page.text(), "整本预览不显示'拼合'区间标注")

    print("2) 改范围后预览跟随")
    row._spin_start.setValue(5)
    row._spin_end.setValue(8)
    check(preview._range == (5, 8), f"范围 {preview._range} == (5, 8)")
    check(preview._current_page == 4, f"当前页跳到范围内首页 (index={preview._current_page})")
    check("拼合 5-8" in preview.label_page.text(), f"页码标注: {preview.label_page.text()!r}")

    print("3) 翻页不越界")
    for _ in range(10):
        preview._prev_page()
    check(preview._current_page == 4, f"向前翻到底停在 index={preview._current_page} (应为 4)")
    check(not preview.btn_prev.isEnabled(), "'上一页'按钮在范围首页被禁用")

    for _ in range(10):
        preview._next_page()
    check(preview._current_page == 7, f"向后翻到底停在 index={preview._current_page} (应为 7)")
    check(not preview.btn_next.isEnabled(), "'下一页'按钮在范围末页被禁用")

    print("4) 范围内改范围不跳页")
    preview._current_page = 6  # 第 7 页
    row._spin_end.setValue(10)
    check(preview._range == (5, 10), f"范围 {preview._range} == (5, 10)")
    check(preview._current_page == 6, f"当前页保持 index={preview._current_page} (应为 6)")

    print("5) 多文件: 改哪一行的范围, 预览就跟到哪一行")
    other_pdf = os.path.join(os.getcwd(), "资料分析模块专项试卷.pdf")
    if not os.path.exists(other_pdf):
        print(f"  [跳过] 缺少第二个测试文件: {os.path.basename(other_pdf)}")
    else:
        window._add_paths([other_pdf])
        window.list_widget.setCurrentRow(0)
        row._spin_start.setValue(5)
        row._spin_end.setValue(8)
        check(preview._range == (5, 8), f"预览跟随第 1 行 {preview._range}")

        other_widget = window.list_widget.item(1).data(Qt.ItemDataRole.UserRole + 1)
        other_widget._spin_end.setValue(3)  # 改第 2 行
        check(window.list_widget.currentRow() == 1, "当前项切到第 2 行")
        check(preview._range == (1, 3), f"预览跟随第 2 行 {preview._range}")

        row._spin_end.setValue(12)  # 再改回第 1 行
        check(window.list_widget.currentRow() == 0, "当前项切回第 1 行")
        check(preview._range == (5, 12), f"预览跟随第 1 行 {preview._range}")
        check(other_widget._spin_start.value() == 1 and other_widget._spin_end.value() == 3,
              "第 2 行自己的范围设置未被打乱, 仍为 1-3")

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项")
        raise SystemExit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
