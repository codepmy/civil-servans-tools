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

# ------------------------------------------------------------
# 枚举默认值（首次使用时写入 mistake_book_config.json，
# 之后由用户通过界面「枚举配置」增删改）
# ------------------------------------------------------------

DEFAULT_REASON_TAGS = ["粗心", "时间压力", "蒙的", "题干读错"]

DEFAULT_CATEGORIES = [
    {"key": "xingce", "name": "行测", "color": "#4F46E5"},
    {"key": "shenlun", "name": "申论", "color": "#B45309"},
]

# 新增科目/模块时自动分配的默认色板（与 Slate + Indigo 设计系统协调）
DEFAULT_COLOR_PALETTE = [
    "#4F46E5", "#0EA5E9", "#16A34A", "#EA580C",
    "#DB2777", "#7C3AED", "#0891B2", "#CA8A04",
]

# 自带的默认模块配色（Tailwind 系，刻意避开上面色板避免撞色）：
# 同一科目内按色相大间隔取色（行测：红/金黄/绿/青/品红/蓝灰；
# 申论：蓝/黄绿/紫/青/玫红），两两 RGB 距离 ≥80，且各自与科目
# 色条（行测 indigo、申论 amber）保持距离，避免相近色难区分。
DEFAULT_SECTION_COLORS = {
    # 行测
    "政治理论": "#DC2626",  # 红
    "常识判断": "#A16207",  # 金黄
    "言语理解": "#15803D",  # 深绿
    "数量关系": "#0284C7",  # 天蓝
    "判断推理": "#D946EF",  # 品红
    "资料分析": "#581C87",  # 深紫
    # 申论
    "归纳概括": "#2563EB",  # 蓝
    "提出对策": "#65A30D",  # 黄绿
    "综合分析": "#9333EA",  # 紫
    "公文写作": "#0D9488",  # 青
    "大作文": "#BE185D",    # 玫红
}

# 未配置颜色的模块回退显示色（中性灰）
DEFAULT_SECTION_COLOR = "#6B7280"

# 新建错题时富文本编辑器的默认输入格式（用户可在「设置 → 默认格式」修改）
# font_family 为空 = 跟随系统默认字体；font_size 为 0 = 跟随编辑器默认字号
DEFAULT_EDITOR_FORMAT = {
    "font_family": "",
    "font_size": 13.0,
    "bold": False,
    "italic": False,
    "underline": False,
    "strikeout": False,
}

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
    note: str = ""              # 标题（字段名保留 note 以兼容旧数据）
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
# 枚举配置：科目 / 模块 / 错因 三维枚举，可增删改
# ------------------------------------------------------------


class MistakeBookConfig:
    """三维枚举的持久化配置（mistake_book_config.json，程序目录）。

    - 科目：key + name + color 结构，数据里存 key，name 仅用于显示
    - 模块：按科目分组（section 数据存名字，约定全局唯一）
    - 错因：全局共用
    缺失或损坏时回退到默认枚举；修改方法调用后立即原子落盘。
    """

    def __init__(self, config_file: Path | None = None):
        self.config_file = Path(config_file) if config_file else data_dir() / "mistake_book_config.json"
        self._data = self._defaults()
        self._load()

    @staticmethod
    def _defaults() -> dict:
        return {
            "categories": [dict(c) for c in DEFAULT_CATEGORIES],
            "sections": {
                "xingce": list(XINGCE_TAGS),
                "shenlun": list(SHENLUN_TAGS),
            },
            "reason_tags": list(DEFAULT_REASON_TAGS),
            "editor_format": dict(DEFAULT_EDITOR_FORMAT),
            # 模块名 → 颜色（模块名约定全局唯一）；缺失时回退默认灰
            "section_colors": dict(DEFAULT_SECTION_COLORS),
        }

    def _load(self):
        if not self.config_file.exists():
            return
        try:
            raw = json.loads(self.config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(raw, dict):
            return
        cats = raw.get("categories")
        if isinstance(cats, list) and cats:
            clean = []
            for c in cats:
                if isinstance(c, dict) and c.get("key"):
                    clean.append({
                        "key": str(c["key"]),
                        "name": str(c.get("name") or c["key"]),
                        "color": str(c.get("color") or "#6B7280"),
                    })
            if clean:
                self._data["categories"] = clean
        secs = raw.get("sections")
        if isinstance(secs, dict):
            for k, v in secs.items():
                if isinstance(v, list):
                    self._data["sections"][str(k)] = [str(x) for x in v]
        tags = raw.get("reason_tags")
        if isinstance(tags, list):
            self._data["reason_tags"] = [str(x) for x in tags]
        colors = raw.get("section_colors")
        if isinstance(colors, dict):
            self._data["section_colors"] = {
                str(k): str(v) for k, v in colors.items()
            }
        # 兼容存量配置：自带的默认模块若尚未配置颜色，补默认色（仅对
        # 当前 sections 中实际存在的模块，不给已删除的模块留孤儿颜色；
        # 用户手动改过的颜色因已存在而不会被覆盖）
        for names in self._data["sections"].values():
            for name in names:
                if name in DEFAULT_SECTION_COLORS and name not in self._data["section_colors"]:
                    self._data["section_colors"][name] = DEFAULT_SECTION_COLORS[name]
        fmt = raw.get("editor_format")
        if isinstance(fmt, dict):
            clean = {}
            family = fmt.get("font_family")
            if isinstance(family, str):
                clean["font_family"] = family
            size = fmt.get("font_size")
            if isinstance(size, (int, float)) and not isinstance(size, bool):
                clean["font_size"] = float(size)
            for key in ("bold", "italic", "underline", "strikeout"):
                if isinstance(fmt.get(key), bool):
                    clean[key] = fmt[key]
            if clean:
                self._data["editor_format"].update(clean)

    def save(self):
        """原子写入配置。"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.config_file)

    # ---- 查询 ----

    def categories(self) -> list[dict]:
        """返回 [{key, name, color}] 副本。"""
        return [dict(c) for c in self._data["categories"]]

    def category_keys(self) -> list[str]:
        return [c["key"] for c in self._data["categories"]]

    def category_name(self, key: str) -> str:
        for c in self._data["categories"]:
            if c["key"] == key:
                return c["name"]
        return key

    def category_color(self, key: str) -> str:
        for c in self._data["categories"]:
            if c["key"] == key:
                return c.get("color") or "#6B7280"
        return "#6B7280"

    def set_category_color(self, key: str, color: str):
        """科目改色（立即落盘）。"""
        for c in self._data["categories"]:
            if c["key"] == key:
                c["color"] = color
                self.save()
                return

    def sections(self, category_key: str) -> list[str]:
        return list(self._data["sections"].get(category_key, []))

    def all_section_names(self) -> list[str]:
        """全部科目的模块名并集（保持配置顺序、去重）。"""
        names: list[str] = []
        for key in self.category_keys():
            for name in self._data["sections"].get(key, []):
                if name not in names:
                    names.append(name)
        return names

    def section_color(self, name: str) -> str:
        """模块显示色：未配置时回退默认灰。"""
        return self._data["section_colors"].get(name) or DEFAULT_SECTION_COLOR

    def set_section_color(self, name: str, color: str):
        """模块改色（立即落盘）。"""
        self._data["section_colors"][name] = color
        self.save()

    def reason_tags(self) -> list[str]:
        return list(self._data["reason_tags"])

    # ---- 默认输入格式 ----

    def editor_format(self) -> dict:
        """返回富文本默认输入格式副本（新建错题时应用）。"""
        return dict(self._data["editor_format"])

    def set_editor_format(self, fmt: dict):
        """更新默认输入格式并落盘（缺省字段保持原值）。"""
        self._data["editor_format"].update(fmt)
        self.save()

    # ---- 科目 ----

    def _next_palette_color(self, used: set[str]) -> str:
        """从预设色板取第一个未被使用的颜色（全部用完则循环取色）。"""
        for color in DEFAULT_COLOR_PALETTE:
            if color not in used:
                return color
        return DEFAULT_COLOR_PALETTE[0]

    def add_category(self, name: str) -> str:
        key = uuid.uuid4().hex[:8]
        # 避开现有科目色与全部模块色，保证新科目色条不与模块文字撞色
        used = {c.get("color") for c in self._data["categories"]}
        used |= set(self._data["section_colors"].values())
        self._data["categories"].append({
            "key": key, "name": name, "color": self._next_palette_color(used),
        })
        self._data["sections"][key] = []
        self.save()
        return key

    def rename_category(self, key: str, new_name: str):
        for c in self._data["categories"]:
            if c["key"] == key:
                c["name"] = new_name
                self.save()
                return

    def remove_category(self, key: str):
        self._data["categories"] = [c for c in self._data["categories"] if c["key"] != key]
        self._data["sections"].pop(key, None)
        self.save()

    # ---- 模块 ----

    def add_section(self, category_key: str, name: str):
        self._data["sections"].setdefault(category_key, []).append(name)
        # 自动分配一个未被使用的色板色（避开现有模块色与科目色；用户可在设置中再改）
        used = set(self._data["section_colors"].values())
        used |= {c.get("color") for c in self._data["categories"]}
        self._data["section_colors"][name] = self._next_palette_color(used)
        self.save()

    def rename_section(self, old_name: str, new_name: str):
        """全局重命名（模块名约定全局唯一），同步迁移颜色配置。"""
        for names in self._data["sections"].values():
            if old_name in names:
                names[names.index(old_name)] = new_name
        if old_name in self._data["section_colors"]:
            self._data["section_colors"][new_name] = self._data["section_colors"].pop(old_name)
        self.save()

    def remove_section(self, category_key: str, name: str):
        names = self._data["sections"].get(category_key, [])
        if name in names:
            names.remove(name)
        self._data["section_colors"].pop(name, None)
        self.save()

    # ---- 错因 ----

    def add_reason_tag(self, name: str):
        self._data["reason_tags"].append(name)
        self.save()

    def rename_reason_tag(self, old_name: str, new_name: str):
        tags = self._data["reason_tags"]
        if old_name in tags:
            tags[tags.index(old_name)] = new_name
        self.save()

    def remove_reason_tag(self, name: str):
        self._data["reason_tags"] = [t for t in self._data["reason_tags"] if t != name]
        self.save()


# ------------------------------------------------------------
# 存储
# ------------------------------------------------------------


class MistakeBookStore:
    """错题本存取：JSON 原子读写 + 增删改查 + 枚举变更迁移。"""

    def __init__(self, data_file: Path | None = None, image_dir: Path | None = None,
                 config: MistakeBookConfig | None = None):
        self.data_file = Path(data_file) if data_file else data_dir() / "mistake_book.json"
        self.image_dir = Path(image_dir) if image_dir else data_dir() / "mistake_images"
        self._config = config or MistakeBookConfig()
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
                # 旧数据迁移：section 为空时，把 tags 中所有枚举模块名提取出来
                # （历史脏数据可能同时含多个模块名，全部移出避免混入错因）
                preset = set(self._config.all_section_names())
                if not it.section:
                    for t in it.tags[:]:
                        if t in preset:
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

    # ---- 枚举变更迁移（配合枚举配置的增删改） ----

    def count_category(self, key: str) -> int:
        return sum(1 for it in self._items if it.category == key)

    def count_section(self, name: str) -> int:
        return sum(1 for it in self._items if it.section == name)

    def count_tag(self, name: str) -> int:
        return sum(1 for it in self._items if name in it.tags)

    def rename_section(self, old_name: str, new_name: str):
        """模块改名：批量更新存量条目的 section。"""
        for it in self._items:
            if it.section == old_name:
                it.section = new_name
        self.save()

    def clear_section(self, name: str):
        """模块删除：存量条目清空对应 section。"""
        for it in self._items:
            if it.section == name:
                it.section = ""
        self.save()

    def rename_tag(self, old_name: str, new_name: str):
        """错因改名：批量替换存量条目的 tags。"""
        for it in self._items:
            if old_name in it.tags:
                it.tags = [new_name if t == old_name else t for t in it.tags]
        self.save()

    def remove_tag(self, name: str):
        """错因删除：存量条目移除该标签。"""
        for it in self._items:
            if name in it.tags:
                it.tags = [t for t in it.tags if t != name]
        self.save()


# ------------------------------------------------------------
# 共享实例
# ------------------------------------------------------------
# 全局「设置 → 错题本枚举」与错题本 widget 必须操作同一份 config/store：
# 枚举变更（重命名/删除）会同步迁移内存中的存量条目，若各自持有实例
# 会导致一边改了配置、另一边的内存数据仍是旧值，再保存时覆盖丢失。

_shared_config: MistakeBookConfig | None = None
_shared_store: MistakeBookStore | None = None


def shared_config() -> MistakeBookConfig:
    """返回应用级共享的 MistakeBookConfig（懒加载单例）。"""
    global _shared_config
    if _shared_config is None:
        _shared_config = MistakeBookConfig()
    return _shared_config


def shared_store() -> MistakeBookStore:
    """返回应用级共享的 MistakeBookStore（懒加载单例，绑定共享 config）。"""
    global _shared_store
    if _shared_store is None:
        _shared_store = MistakeBookStore(config=shared_config())
    return _shared_store
