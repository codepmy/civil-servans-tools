"""错题本数据层：数据模型 + JSON 存取 + 增删改查 + 图片落盘。

数据保存在「程序目录」下（源码运行时为项目根目录，打包后为 exe 所在目录）：
    mistake_book.json       错题列表（原子写入，防损坏）
    mistake_images/         粘贴的截图（按条目分文件存放）

富文本约定：MistakeItem.content 为 HTML 富文本；其中粘贴的图片以
`src="<文件名>"` 引用 mistake_images/ 下的文件，避免把 base64 图片
直接塞进 JSON 导致文件膨胀。
"""

import base64
import json
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------
# 标签预设
# ------------------------------------------------------------

XINGCE_TAGS = ["政治理论", "常识判断", "言语理解", "数量关系", "判断推理", "资料分析"]
SHENLUN_TAGS = ["归纳概括", "提出对策", "综合分析", "公文写作", "大作文"]

CATEGORY_NAMES = {"xingce": "行测", "shenlun": "申论"}

# 全部预置模块名（用于旧数据迁移：从 tags 中提取模块）
PRESET_SECTIONS = set(XINGCE_TAGS + SHENLUN_TAGS)

# ------------------------------------------------------------
# 路径解析：数据存在程序安装目录
# ------------------------------------------------------------


def data_dir() -> Path:
    """返回可写的数据目录：打包后为 exe 所在目录，源码运行时为项目根目录。

    注意：打包后 exe 目录内必有 exe 文件，目录本身可写才保证能落盘。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # tools/mistake_book/core/mistake_book.py -> parents[3] = 项目根目录
    return Path(__file__).resolve().parents[3]


# ------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------


@dataclass
class MistakeItem:
    """一道错题记录。"""

    id: str
    content: str                # 富文本 HTML（图片 src 为相对文件名）
    category: str = "xingce"    # 大标签: "xingce" | "shenlun"
    section: str = ""           # 模块（单值）：如 "数量关系"
    tags: list[str] = field(default_factory=list)  # 错因标签（集合）
    my_answer: str = ""         # 我的答案
    correct_answer: str = ""    # 正确答案
    corrected: bool = False     # 是否已订正
    note: str = ""              # 备注
    created_at: str = ""        # "YYYY-MM-DD HH:MM"
    updated_at: str = ""

    @staticmethod
    def now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]


# ------------------------------------------------------------
# 富文本图片处理：base64 <-> 文件
# ------------------------------------------------------------

_IMG_DATA_RE = re.compile(r'src="data:image/(png|jpeg|jpg);base64,([^"]+)"')
_IMG_FILE_RE = re.compile(r'src="([^"]+\.(?:png|jpe?g))"')


def extract_images_from_html(html: str, image_dir: Path, prefix: str) -> str:
    """把 HTML 内嵌的 base64 图片落盘，src 替换为文件名引用，返回新 HTML。

    prefix 通常用条目 id，图片命名 `<prefix>_<n>.<ext>`。
    """
    if not html:
        return html
    image_dir.mkdir(parents=True, exist_ok=True)
    counter = {"n": 0}

    def repl(match: re.Match) -> str:
        ext = "png" if match.group(1) == "png" else "jpg"
        raw = match.group(2)
        counter["n"] += 1
        name = f"{prefix}_{counter['n']}.{ext}"
        try:
            (image_dir / name).write_bytes(base64.b64decode(raw))
        except (ValueError, OSError):
            return match.group(0)  # 解码失败保持原样
        return f'src="{name}"'

    return _IMG_DATA_RE.sub(repl, html)


def embed_images_in_html(html: str, image_dir: Path) -> str:
    """加载时反向：把文件名引用替换回 data URI，供 QTextEdit 显示。"""
    if not html:
        return html

    def repl(match: re.Match) -> str:
        name = match.group(1)
        path = image_dir / name
        if path.is_file():
            try:
                b64 = base64.b64encode(path.read_bytes()).decode()
                return f'src="data:image/png;base64,{b64}"'
            except OSError:
                pass
        return match.group(0)

    return _IMG_FILE_RE.sub(repl, html)


def collect_image_names(html: str) -> list[str]:
    """提取 HTML 中引用的图片文件名（用于删除条目时清理文件）。"""
    return [m.group(1) for m in _IMG_FILE_RE.finditer(html or "")]


def text_preview(html: str, max_len: int = 60) -> str:
    """富文本 HTML → 纯文本摘要（去掉标签、样式块与图片引用）。

    Qt 的 toHtml 输出带 <style>/<head> 块，需先整块剔除再剥标签。
    """
    text = html or ""
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<head[^>]*>.*?</head>", "", text, flags=re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    for src, dst in (
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"),
    ):
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


# ------------------------------------------------------------
# 存储
# ------------------------------------------------------------


class MistakeBookStore:
    """错题本存取：JSON 原子读写 + 增删改查。"""

    def __init__(self, data_file: Path | None = None, image_dir: Path | None = None):
        self.data_file = Path(data_file) if data_file else data_dir() / "mistake_book.json"
        self.image_dir = Path(image_dir) if image_dir else data_dir() / "mistake_images"
        self._migrate_legacy_paths()
        self._items: list[MistakeItem] = []
        self._load()

    def _migrate_legacy_paths(self):
        """早期版本把数据误存到 tools/ 下，首次启动时自动迁移到数据目录。"""
        if self.data_file.exists():
            return
        legacy_dir = Path(__file__).resolve().parents[2]  # tools/
        legacy_file = legacy_dir / "mistake_book.json"
        if not legacy_file.exists():
            return
        try:
            legacy_file.replace(self.data_file)
            legacy_images = legacy_dir / "mistake_images"
            if legacy_images.exists():
                legacy_images.rename(self.image_dir)
        except OSError:
            # 迁移失败：把已移动的 JSON 移回原位，下次启动再试，
            # 避免 JSON 与图片目录分家导致图片引用丢失
            try:
                if self.data_file.exists() and not legacy_file.exists():
                    self.data_file.replace(legacy_file)
            except OSError:
                pass

    # ---- 读写 ----

    def _load(self):
        if not self.data_file.exists():
            return
        try:
            raw = json.loads(self.data_file.read_text(encoding="utf-8"))
            items = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                fields = {k: v for k, v in item.items() if k in MistakeItem.__dataclass_fields__}
                it = MistakeItem(**fields)
                # 旧数据迁移：section 为空时，把 tags 中所有预置模块名提取出来
                # （历史脏数据可能同时含多个模块名，全部移出避免混入错因）
                if not it.section:
                    for t in it.tags[:]:
                        if t in PRESET_SECTIONS:
                            if not it.section:
                                it.section = t
                            it.tags.remove(t)
                items.append(it)
            self._items = items
        except (json.JSONDecodeError, OSError, TypeError):
            # 文件损坏：备份后重置，避免程序打不开
            try:
                self.data_file.rename(self.data_file.with_suffix(".json.bak"))
            except OSError:
                pass
            self._items = []

    def save(self):
        """原子写入：先写临时文件再替换，防止写入中断损坏数据。"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.data_file.with_suffix(".json.tmp")
        payload = json.dumps([asdict(item) for item in self._items],
                             ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.data_file)

    # ---- 查询 ----

    def all_items(self) -> list[MistakeItem]:
        """按最近更新排序返回全部条目。"""
        return sorted(self._items, key=lambda it: it.updated_at, reverse=True)

    def get(self, item_id: str) -> MistakeItem | None:
        return next((it for it in self._items if it.id == item_id), None)

    def count(self) -> int:
        return len(self._items)

    # ---- 增删改 ----

    def add(self, item: MistakeItem):
        self._items.append(item)
        self.save()

    def update(self, item: MistakeItem):
        for i, existing in enumerate(self._items):
            if existing.id == item.id:
                self._items[i] = item
                self.save()
                return

    def delete(self, item_id: str):
        item = self.get(item_id)
        if item is None:
            return
        self._items = [it for it in self._items if it.id != item_id]
        # 清理该条目引用的图片文件
        for name in collect_image_names(item.content):
            try:
                (self.image_dir / name).unlink(missing_ok=True)
            except OSError:
                pass
        self.save()
