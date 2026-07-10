"""中文字体管理器: 发现、注册和回退Windows系统字体。"""

import os
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont


class FontManager:
    """管理中文TrueType字体的发现、注册和回退。"""

    KNOWN_FONTS = {
        "SimSun": ("simsun.ttc", 0),
        "SimHei": ("simhei.ttf", 0),
        "KaiTi": ("simkai.ttf", 0),
        "FangSong": ("simfang.ttf", 0),
        "Microsoft YaHei": ("msyh.ttc", 0),
        "Microsoft YaHei Bold": ("msyhbd.ttc", 0),
        "Microsoft JhengHei": ("msjh.ttc", 0),
        "DengXian": ("Deng.ttf", 0),
        "DengXian Bold": ("Dengb.ttf", 0),
        "YouYuan": ("simyou.ttf", 0),
        "LiSu": ("SIMLI.TTF", 0),
        "STXingkai": ("STXINGKA.TTF", 0),
    }

    FALLBACK_CHAIN = {
        "SimSun": ["FangSong", "KaiTi", "Microsoft YaHei"],
        "SimHei": ["Microsoft YaHei", "SimSun"],
        "KaiTi": ["FangSong", "SimSun"],
        "FangSong": ["KaiTi", "SimSun"],
        "Microsoft YaHei": ["SimHei", "SimSun"],
        "Microsoft JhengHei": ["Microsoft YaHei", "SimSun"],
        "DengXian": ["Microsoft YaHei", "SimSun"],
        "YouYuan": ["SimSun", "Microsoft YaHei"],
    }

    def __init__(self):
        self._fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        self._available: dict[str, str] = {}
        self._registered: set[str] = set()
        self._discover()

    def _discover(self):
        """发现系统中可用的中文字体。"""
        for name, (filename, _) in self.KNOWN_FONTS.items():
            font_path = self._fonts_dir / filename
            if font_path.exists():
                self._available[name] = str(font_path)

        # 把常见中文/CJK字体也纳入下拉框，避免只能看到少数内置名称。
        keywords = (
            "simsun", "simhei", "simkai", "simfang", "simyou", "msyh", "msjh",
            "deng", "songti", "heiti", "kaiti", "fangsong", "cjk", "noto",
            "sourcehan", "adobesong", "adobeheit", "adobefangsong", "adobekaiti",
            "stfangsong", "stkaiti", "stheiti", "stsong", "fz", "hanyi",
        )
        for ext in ("*.ttf", "*.ttc", "*.otf"):
            for font_file in self._fonts_dir.glob(ext):
                if font_file.stat().st_size < 10_000:
                    continue
                key = font_file.stem.lower().replace(" ", "")
                if any(kw in key for kw in keywords):
                    name = self._friendly_name(font_file)
                    self._available.setdefault(name, str(font_file))

    @staticmethod
    def _friendly_name(path: Path) -> str:
        aliases = {
            "simsun": "SimSun",
            "simhei": "SimHei",
            "simkai": "KaiTi",
            "simfang": "FangSong",
            "msyh": "Microsoft YaHei",
            "msyhbd": "Microsoft YaHei Bold",
            "msjh": "Microsoft JhengHei",
            "deng": "DengXian",
            "dengb": "DengXian Bold",
            "simyou": "YouYuan",
        }
        return aliases.get(path.stem.lower(), path.stem)

    def register_all(self):
        """向ReportLab注册所有可用字体。"""
        for name, path in list(self._available.items()):
            try:
                if name not in self._registered:
                    _, index = self.KNOWN_FONTS.get(name, (Path(path).name, 0))
                    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
                    self._registered.add(name)
            except Exception as e:
                print(f"Warning: Failed to register font {name}: {e}")

        try:
            if "Microsoft YaHei" in self._registered and "Microsoft YaHei Bold" in self._registered:
                registerFontFamily(
                    "Microsoft YaHei",
                    normal="Microsoft YaHei",
                    bold="Microsoft YaHei Bold",
                )
        except Exception:
            pass

    def register_font(self, name: str, path: str, index: int = 0):
        """手动注册一个字体。"""
        try:
            if name not in self._registered:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
                self._registered.add(name)
                self._available[name] = path
        except Exception as e:
            print(f"Warning: Failed to register font {name}: {e}")

    def get_fallback(self, preferred: str) -> str:
        """获取最佳可用字体。"""
        if preferred in self._available and preferred in self._registered:
            return preferred

        if preferred in self._available:
            try:
                self.register_font(preferred, self._available[preferred])
                return preferred
            except Exception:
                pass

        chain = self.FALLBACK_CHAIN.get(preferred, [])
        for fb in chain:
            if fb in self._available:
                return fb

        for name in self._available:
            if name in self._registered:
                return name

        if self._available:
            first = next(iter(self._available))
            self.register_font(first, self._available[first])
            return first

        raise RuntimeError(
            "未找到任何中文字体！\n"
            "请确保系统安装了以下字体之一: SimSun(宋体), SimHei(黑体), "
            "KaiTi(楷体), Microsoft YaHei(微软雅黑)"
        )

    def available_fonts(self) -> list[str]:
        """返回所有可用字体名称列表。"""
        preferred = [name for name in self.KNOWN_FONTS if name in self._available]
        extra = sorted(name for name in self._available if name not in self.KNOWN_FONTS)
        return preferred + extra

    def has_font(self, name: str) -> bool:
        """检查字体是否可用。"""
        return name in self._available

    def get_font_path(self, name: str) -> str | None:
        """获取字体文件路径。"""
        return self._available.get(name)
