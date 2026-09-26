"""复现/验证 PDF 拼合列表的"外部文件拖放"事件处理。

用法:
    python tools/pdf_merger/dev/check_drop.py

构造一个带本地 PDF URL 的拖放事件, 直接喂给 DropListWidget, 检查
dragEnter -> drop 之后 files_added 信号是否发出。
"""

import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QApplication

from tools.pdf_merger.ui.widget import DropListWidget, PdfMergerWidget


def make_mime(paths: list[str]) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return mime


def send_drag(widget, mime: QMimeData) -> None:
    """把 dragEnter + drop 走一遍, 返回 None。"""
    pos = QPointF(20, 20)
    enter = QDragEnterEvent(
        pos.toPoint(), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    widget.dragEnterEvent(enter)
    drop = QDropEvent(
        pos, Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    widget.dropEvent(drop)


def check_signal(pdf: str) -> int:
    """第一层: DropListWidget 是否发出 files_added。"""
    widget = DropListWidget()
    received: list[list[str]] = []
    widget.files_added.connect(received.append)
    send_drag(widget, make_mime([pdf]))
    if not received:
        print("  [失败] files_added 未发出 —— 文件拖进去不会显示")
        return 1
    print(f"  [通过] files_added -> {len(received[0])} 个路径")
    return 0


def check_end_to_end(pdf: str) -> int:
    """第二层: 完整 PdfMergerWidget 拖放后, 列表里是否真的多出一项。"""
    window = PdfMergerWidget()
    before = window.list_widget.count()
    send_drag(window.list_widget, make_mime([pdf]))
    after = window.list_widget.count()
    if after != before + 1:
        print(f"  [失败] 列表项数 {before} -> {after}, 文件未加入")
        return 1
    stored = window.list_widget.item(after - 1).data(Qt.ItemDataRole.UserRole)
    print(f"  [通过] 列表项数 {before} -> {after}, 末项={Path(stored).name if stored else None}")

    # 重复拖同一文件不应重复添加
    send_drag(window.list_widget, make_mime([pdf]))
    if window.list_widget.count() != after:
        print("  [失败] 重复拖放同一文件被重复添加")
        return 1
    print("  [通过] 重复拖放同一文件被忽略")
    return 0


def check_internal_reorder(pdf: str) -> int:
    """第三层: 列表内部拖拽重排的信号链路不能受影响。

    内部拖拽的 mimeData 没有 urls, 应落到分支之外 —— 交给基类处理并发出
    order_changed; 若被外部文件分支吞掉, 重排就会失效。
    """
    widget = DropListWidget()
    widget.addItem("占位项")
    order: list[int] = []
    widget.order_changed.connect(lambda: order.append(1))

    # 内部拖拽不会带 urls
    internal_mime = QMimeData()
    send_drag(widget, internal_mime)

    if not order:
        print("  [失败] 内部拖拽没有发出 order_changed, 重排会失效")
        return 1
    print("  [通过] 内部拖拽仍发出 order_changed")
    return 0


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841  (QApplication 必须活着)

    fake_pdf = os.path.join(os.getcwd(), "行测套卷.pdf")
    if not os.path.exists(fake_pdf):
        print(f"找不到测试文件: {fake_pdf}")
        raise SystemExit(1)

    print("1) DropListWidget 信号层")
    code = check_signal(fake_pdf)
    print("2) PdfMergerWidget 端到端")
    code |= check_end_to_end(fake_pdf)
    print("3) 内部拖拽重排")
    code |= check_internal_reorder(fake_pdf)
    print("全部通过" if code == 0 else "存在失败项")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
