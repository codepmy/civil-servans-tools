"""内置时政数据源注册表。"""

from __future__ import annotations

from typing import Iterable

from .base import BaseNewsSource
from .gov_cn import GovCnSource
from .people_daily import PeopleDailySource
from .xinhua import XinhuaSource

__all__ = [
    "BaseNewsSource",
    "GovCnSource",
    "XinhuaSource",
    "PeopleDailySource",
    "default_sources",
]


def default_sources() -> list[BaseNewsSource]:
    """默认启用全部官方三源。"""
    return [GovCnSource(), XinhuaSource(), PeopleDailySource()]
