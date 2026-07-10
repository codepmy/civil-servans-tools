"""配置加载器: 读取和验证排版模板配置。"""

import json
import os
from pathlib import Path


# 默认模板目录
TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_template(exam_type: str) -> dict:
    """加载指定类型的排版模板。

    Args:
        exam_type: "xingce" 或 "shenlun"

    Returns:
        模板配置字典
    """
    filename = f"{exam_type}_template.json"
    path = TEMPLATES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"模板文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_default_config(exam_type: str) -> dict:
    """加载默认配置(等同于load_template，未来可扩展预设系统)。"""
    return load_template(exam_type)


def get_available_fonts() -> list[str]:
    """获取Windows系统中可用的中文字体列表。"""
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    common_chinese_fonts = [
        ("SimSun", "simsun.ttc"),
        ("SimHei", "simhei.ttf"),
        ("KaiTi", "simkai.ttf"),
        ("FangSong", "simfang.ttf"),
        ("Microsoft YaHei", "msyh.ttc"),
        ("Microsoft YaHei Bold", "msyhbd.ttc"),
    ]
    available = []
    for name, filename in common_chinese_fonts:
        if (fonts_dir / filename).exists():
            available.append(name)
    return available
