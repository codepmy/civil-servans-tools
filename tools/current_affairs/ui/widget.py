"""每日时政主界面：日期导航 + 来源/分类筛选 + 新闻列表 + 内嵌阅读详情。"""

from __future__ import annotations

from PyQt6.QtCore import QSize, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from tools.current_affairs.core.cache import NewsCache
from tools.current_affairs.core.dates import add_days, display_date, is_stale, today_str
from tools.current_affairs.core.models import (
    ALL_CATEGORIES,
    CATEGORY_NEWS,
    CATEGORY_OTHER,
    CATEGORY_POLICY,
    CATEGORY_SPEECH,
    NewsItem,
)
from tools.current_affairs.core.sources import default_sources
from tools.current_affairs.ui.worker import ArticleFetchWorker, FetchWorker
from ui.dialogs import show_success

# ============================================================
# 设计令牌（Slate + Indigo，与全局 QSS 一致）
# ============================================================

CARD_STYLE = (
    "QWidget#card { background-color: #FFFFFF; border: 1px solid #E5E7EB;"
    " border-radius: 10px; }"
)

PRIMARY_BTN = (
    "QPushButton { background-color: #4F46E5; color: #FFFFFF; border: none;"
    " border-radius: 6px; padding: 6px 14px; font-size: 13px; font-weight: 600;"
    " min-height: 30px; }"
    "QPushButton:hover { background-color: #4338CA; }"
    "QPushButton:pressed { background-color: #3730A3; }"
    "QPushButton:disabled { background-color: #C7D2FE; color: #FFFFFF; }"
)

SECONDARY_BTN = (
    "QPushButton { background-color: #FFFFFF; border: 1px solid #D1D5DB;"
    " border-radius: 6px; padding: 5px 12px; color: #374151; font-size: 12px;"
    " font-weight: 500; min-height: 28px; }"
    "QPushButton:hover { background-color: #F9FAFB; border-color: #9CA3AF; }"
    "QPushButton:disabled { color: #D1D5DB; background-color: #F9FAFB; }"
)

ICON_BTN = (
    "QPushButton { background-color: #F3F4F6; border: 1px solid #E5E7EB;"
    " border-radius: 6px; padding: 3px 10px; color: #374151; font-size: 12px;"
    " min-height: 26px; }"
    "QPushButton:hover { background-color: #E5E7EB; }"
    "QPushButton:disabled { color: #D1D5DB; }"
)

NEWS_LIST_STYLE = (
    "QListWidget { border: none; background: transparent; outline: none;"
    " padding: 2px; }"
    "QListWidget::item { background: transparent; border: none; margin: 2px 0px;"
    " border-radius: 8px; }"
    "QListWidget::item:selected { background: #EEF2FF; }"
    "QListWidget::item:hover { background: #F9FAFB; }"
)

# 分类徽标配色
CATEGORY_COLORS = {
    CATEGORY_POLICY: ("#4F46E5", "#EEF2FF"),   # 靛蓝
    CATEGORY_NEWS: ("#2563EB", "#EFF6FF"),     # 蓝
    CATEGORY_SPEECH: ("#DC2626", "#FEF2F2"),   # 红
    CATEGORY_OTHER: ("#6B7280", "#F3F4F6"),    # 灰
}


def _category_badge_style(category: str) -> str:
    fg, bg = CATEGORY_COLORS.get(category, CATEGORY_COLORS[CATEGORY_OTHER])
    return (
        f"QLabel {{ background-color: {bg}; color: {fg}; border-radius: 4px;"
        f" padding: 2px 8px; font-size: 11px; font-weight: 600; }}"
    )


TAG_BADGE_STYLE = (
    "QLabel { background-color: #FEF3C7; color: #92400E; border-radius: 4px;"
    " padding: 1px 7px; font-size: 10px; font-weight: 500; }"
)

FAV_STAR_STYLE = "QLabel { font-size: 12px; color: #F59E0B; background: transparent; }"


class _NewsList(QListWidget):
    """新闻列表：分隔条移动时按新宽度重算行高，避免换行标题被裁剪。"""

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._remeasure_rows()

    def _remeasure_rows(self) -> None:
        width = max(self.viewport().width(), 320)
        for i in range(self.count()):
            list_item = self.item(i)
            row = self.itemWidget(list_item)
            if isinstance(row, _NewsRow):
                row._list_width = width
                list_item.setSizeHint(row.sizeHint())


class _NewsRow(QWidget):
    """新闻列表行：分类徽标 + 标题 + 来源·时间（+ 考点徽标 + 收藏星标）。"""

    def __init__(self, item: NewsItem, is_fav: bool, list_width: int = 400, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._list_width = max(list_width, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addStretch()

        badge = QLabel(item.category)
        badge.setStyleSheet(_category_badge_style(item.category))
        top.addWidget(badge)

        for tag in item.tags[:3]:
            chip = QLabel(tag)
            chip.setStyleSheet(TAG_BADGE_STYLE)
            top.addWidget(chip)

        if is_fav:
            star = QLabel("★")
            star.setStyleSheet(FAV_STAR_STYLE)
            top.addWidget(star)

        layout.addLayout(top)

        self.title_label = QLabel(item.title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #1F2937;"
            "background: transparent; border: none; padding: 0;"
        )
        layout.addWidget(self.title_label)

        meta = QLabel(item.display_meta)
        meta.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent;"
            "border: none; padding: 0;"
        )
        layout.addWidget(meta)

    def sizeHint(self) -> QSize:
        """按当前列表宽度计算标题换行后的行高。"""
        fm = self.title_label.fontMetrics()
        wrapped = fm.boundingRect(
            0, 0, self._list_width - 24, 2000,
            Qt.TextFlag.TextWordWrap, self.title_label.text(),
        )
        height = 10 + 18 + 4 + wrapped.height() + 4 + 16 + 10
        return QSize(self._list_width, max(68, height))


class CurrentAffairsWidget(QWidget):
    """每日时政主界面。

    信号：
    - ``back_requested``：点击返回
    - ``status_message``：状态栏消息
    """

    back_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    STALE_HOURS = 6.0  # 缓存超过 6 小时自动刷新

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache = NewsCache()
        self._fetch_worker: FetchWorker | None = None
        self._article_worker: ArticleFetchWorker | None = None
        self._current_date = today_str()
        self._all_items: list[NewsItem] = []
        self._displayed_items: list[NewsItem] = []
        self._selected: NewsItem | None = None

        self._setup_ui()
        self._load_initial()

    # ================================================================
    # UI 构建
    # ================================================================

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        page = QWidget()
        page.setObjectName("tool-page")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(12, 12, 12, 12)
        page_layout.setSpacing(10)

        page_layout.addWidget(self._build_top_bar())
        page_layout.addWidget(self._build_date_bar())
        page_layout.addWidget(self._build_body(), stretch=1)
        page_layout.addWidget(self._build_status_bar())

        root.addWidget(page)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("card")
        bar.setStyleSheet(CARD_STYLE)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        self.btn_back = QPushButton("← 返回")
        self.btn_back.setStyleSheet(SECONDARY_BTN)
        self.btn_back.clicked.connect(self.back_requested.emit)
        layout.addWidget(self.btn_back)

        title = QLabel("📰 每日时政")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1F2937;")
        layout.addWidget(title)

        layout.addStretch()

        self.btn_export = QPushButton("导出 TXT")
        self.btn_export.setStyleSheet(SECONDARY_BTN)
        self.btn_export.clicked.connect(self._on_export)
        layout.addWidget(self.btn_export)

        self.chk_fav = QCheckBox("仅看收藏")
        self.chk_fav.setStyleSheet("font-size: 12px; color: #374151;")
        self.chk_fav.toggled.connect(self._apply_filters)
        layout.addWidget(self.chk_fav)

        self.combo_source = QComboBox()
        self.combo_source.addItem("全部来源", "")
        for source in default_sources():
            self.combo_source.addItem(source.source_name, source.source_id)
        self.combo_source.setStyleSheet("font-size: 12px; min-width: 92px;")
        self.combo_source.currentIndexChanged.connect(self._apply_filters)
        layout.addWidget(self.combo_source)

        self.combo_category = QComboBox()
        self.combo_category.addItem("全部分类", "")
        for cat in ALL_CATEGORIES:
            self.combo_category.addItem(cat, cat)
        self.combo_category.setStyleSheet("font-size: 12px; min-width: 92px;")
        self.combo_category.currentIndexChanged.connect(self._apply_filters)
        layout.addWidget(self.combo_category)

        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("搜索标题…")
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.setStyleSheet(
            "QLineEdit { font-size: 12px; border: 1px solid #D1D5DB;"
            " border-radius: 6px; padding: 4px 10px; min-width: 140px; }"
            "QLineEdit:focus { border-color: #4F46E5; }"
        )
        self.edit_search.textChanged.connect(self._apply_filters)
        layout.addWidget(self.edit_search)

        self.btn_refresh = QPushButton("↻ 刷新")
        self.btn_refresh.setStyleSheet(PRIMARY_BTN)
        self.btn_refresh.clicked.connect(self._on_refresh)
        layout.addWidget(self.btn_refresh)

        return bar

    def _build_date_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(8)

        self.btn_prev = QPushButton("◀ 前一天")
        self.btn_prev.setStyleSheet(ICON_BTN)
        self.btn_prev.clicked.connect(lambda: self._change_date(-1))
        layout.addWidget(self.btn_prev)

        self.lbl_date = QLabel("")
        self.lbl_date.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #374151; padding: 0 6px;"
        )
        layout.addWidget(self.lbl_date)

        self.btn_next = QPushButton("后一天 ▶")
        self.btn_next.setStyleSheet(ICON_BTN)
        self.btn_next.clicked.connect(lambda: self._change_date(1))
        layout.addWidget(self.btn_next)

        self.btn_today = QPushButton("回到今天")
        self.btn_today.setStyleSheet(ICON_BTN)
        self.btn_today.clicked.connect(self._go_today)
        layout.addWidget(self.btn_today)

        layout.addStretch()

        self.lbl_cache_hint = QLabel("")
        self.lbl_cache_hint.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        layout.addWidget(self.lbl_cache_hint)

        return bar

    def _build_body(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 左侧：新闻列表 ──
        self.list_widget = _NewsList()
        self.list_widget.setStyleSheet(NEWS_LIST_STYLE)
        self.list_widget.setSpacing(2)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        splitter.addWidget(self.list_widget)

        # ── 右侧：详情 ──
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(4, 0, 0, 0)
        detail_layout.setSpacing(8)

        self.lbl_detail_title = QLabel("点击左侧新闻查看详情")
        self.lbl_detail_title.setWordWrap(True)
        self.lbl_detail_title.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #1F2937;"
        )
        detail_layout.addWidget(self.lbl_detail_title)

        self.lbl_detail_meta = QLabel("")
        self.lbl_detail_meta.setWordWrap(True)
        self.lbl_detail_meta.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        detail_layout.addWidget(self.lbl_detail_meta)

        self.lbl_detail_tags = QLabel("")
        self.lbl_detail_tags.setStyleSheet("font-size: 11px; color: #92400E;")
        detail_layout.addWidget(self.lbl_detail_tags)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_open = QPushButton("🔗 阅读原文")
        self.btn_open.setStyleSheet(SECONDARY_BTN)
        self.btn_open.clicked.connect(self._on_open_browser)
        btn_row.addWidget(self.btn_open)

        self.btn_fav = QPushButton("☆ 收藏")
        self.btn_fav.setStyleSheet(SECONDARY_BTN)
        self.btn_fav.clicked.connect(self._on_toggle_favorite)
        btn_row.addWidget(self.btn_fav)
        btn_row.addStretch()
        detail_layout.addLayout(btn_row)

        self.content_view = QTextBrowser()
        self.content_view.setOpenExternalLinks(False)
        self.content_view.setStyleSheet(
            "QTextBrowser { border: 1px solid #E5E7EB; border-radius: 8px;"
            " background-color: #FFFFFF; font-size: 14px; color: #374151;"
            " padding: 8px; }"
        )
        detail_layout.addWidget(self.content_view, stretch=1)

        splitter.addWidget(detail)
        splitter.setSizes([430, 700])

        return splitter

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            "QFrame { background-color: #F9FAFB; border: 1px solid #F3F4F6;"
            " border-radius: 8px; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("font-size: 12px; color: #6B7280;")
        layout.addWidget(self.lbl_status)
        layout.addStretch()
        return bar

    # ================================================================
    # 生命周期
    # ================================================================

    def _load_initial(self) -> None:
        self._load_date(today_str())

    def on_enter(self) -> None:
        """主窗口切换到本页时调用：加载当天缓存，过期则自动刷新。"""
        if self._current_date != today_str():
            self._go_today()
            return
        self._refresh_view()
        updated = self._cache.updated_at(self._current_date)
        if is_stale(updated, self.STALE_HOURS):
            self._start_fetch()

    # ================================================================
    # 日期导航
    # ================================================================

    def _load_date(self, date_str: str) -> None:
        self._current_date = date_str
        cached = self._cache.get_day(date_str)
        if cached:
            self._all_items = cached
            self.lbl_cache_hint.setText(
                f"缓存于 {self._cache.updated_at(date_str)}" if self._cache.updated_at(date_str) else ""
            )
        else:
            self._all_items = []
            self.lbl_cache_hint.setText("该日期暂无数据" if date_str != today_str() else "首次使用，点击「刷新」获取今日时政")
        self._selected = None
        self._apply_filters()
        self._update_date_label()
        self._render_detail(None)

    def _change_date(self, delta: int) -> None:
        target = add_days(self._current_date, delta)
        if target > today_str():
            return
        self._load_date(target)

    def _go_today(self) -> None:
        if self._current_date != today_str():
            self._load_date(today_str())
        self._start_fetch()

    def _refresh_view(self) -> None:
        """重新从缓存加载当前日期并刷新界面。"""
        self._all_items = self._cache.get_day(self._current_date)
        self._apply_filters()
        self._update_date_label()
        self._render_detail(self._selected)

    def _update_date_label(self) -> None:
        self.lbl_date.setText(display_date(self._current_date))
        self.btn_next.setEnabled(self._current_date < today_str())
        self.btn_today.setVisible(self._current_date != today_str())

    # ================================================================
    # 抓取
    # ================================================================

    def _on_refresh(self) -> None:
        self._load_date(today_str())
        self._start_fetch()

    def _start_fetch(self) -> None:
        if self._fetch_worker and self._fetch_worker.isRunning():
            self._set_status("正在抓取中，请稍候…")
            return
        if not self._check_deps():
            return
        self.btn_refresh.setEnabled(False)
        self._set_status("正在抓取最新时政（政府网/新华网/人民网）…")
        self._fetch_worker = FetchWorker(self._current_date)
        self._fetch_worker.progress.connect(self._set_status)
        self._fetch_worker.succeeded.connect(self._on_fetch_succeeded)
        self._fetch_worker.failed.connect(self._on_fetch_failed)
        self._fetch_worker.finished.connect(self._on_fetch_finished)
        self._fetch_worker.start()

    def _on_fetch_succeeded(self, result: dict) -> None:
        fetch_date: str = result["date"]
        items: list[NewsItem] = result["items"]
        errors: list[str] = result["errors"]
        sources_ok = result["sources_ok"]
        sources_total = result["sources_total"]

        self._cache.set_day(fetch_date, items)
        if fetch_date == self._current_date:
            self._all_items = items
            self._selected = None
            self._apply_filters()
            self._update_date_label()

        if sources_ok == 0:
            self._set_status(f"抓取失败：{'；'.join(errors[:2])}")
        else:
            hint = f"成功 {sources_ok}/{sources_total}"
            if errors:
                hint += f"，失败来源：{'、'.join(_error_source(err) for err in errors)}"
            self._set_status(f"已更新 {len(items)} 条时政（{hint}）")

    def _on_fetch_failed(self, message: str) -> None:
        self._set_status(f"抓取失败：{message}")

    def _on_fetch_finished(self) -> None:
        if self._fetch_worker:
            self._fetch_worker.deleteLater()
        self._fetch_worker = None
        self.btn_refresh.setEnabled(True)

    # ================================================================
    # 列表与筛选
    # ================================================================

    def _apply_filters(self) -> None:
        source_id = self.combo_source.currentData() or ""
        category = self.combo_category.currentData() or ""
        keyword = self.edit_search.text().strip()
        only_fav = self.chk_fav.isChecked()

        favorites = {fav.url for fav in self._cache.favorites()}
        filtered: list[NewsItem] = []
        for item in self._all_items:
            if source_id and item.source != source_id:
                continue
            if category and item.category != category:
                continue
            if keyword and keyword not in item.title:
                continue
            if only_fav and item.url not in favorites:
                continue
            filtered.append(item)

        self._displayed_items = filtered
        self._repopulate_list(favorites)

    def _repopulate_list(self, favorites: set[str]) -> None:
        self.list_widget.clear()
        if not self._displayed_items:
            empty = QListWidgetItem("暂无匹配内容")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(empty)
            return
        for item in self._displayed_items:
            list_item = QListWidgetItem()
            row = _NewsRow(item, item.url in favorites)
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            list_item.setSizeHint(row.sizeHint())
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, row)

    # ================================================================
    # 详情与正文
    # ================================================================

    def _on_item_clicked(self, list_item: QListWidgetItem) -> None:
        item = list_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(item, NewsItem):
            self._selected = item
            self._render_detail(item)
            if not item.content:
                self._start_article_fetch(item.url)

    def _render_detail(self, item: NewsItem | None) -> None:
        if item is None:
            self.lbl_detail_title.setText("点击左侧新闻查看详情")
            self.lbl_detail_meta.setText("")
            self.lbl_detail_tags.setText("")
            self.btn_open.setEnabled(False)
            self.btn_fav.setEnabled(False)
            self.content_view.setPlainText("")
            return

        self.lbl_detail_title.setText(item.title)
        self.lbl_detail_meta.setText(
            f"分类：{item.category}　|　来源：{item.source_name}　|　时间：{item.published_at or '未知'}"
        )
        self.lbl_detail_tags.setText(
            "考点：" + " / ".join(item.tags) if item.tags else ""
        )
        self.btn_open.setEnabled(True)
        self.btn_fav.setEnabled(True)
        self.btn_fav.setText("★ 已收藏" if self._cache.is_favorite(item.url) else "☆ 收藏")

        if item.content:
            self.content_view.setPlainText(item.content)
        elif item.summary:
            self.content_view.setPlainText(f"（暂无正文，以下为摘要）\n\n{item.summary}\n\n正文加载中…")
        else:
            self.content_view.setPlainText("正在加载正文…")

    def _start_article_fetch(self, url: str) -> None:
        if self._article_worker and self._article_worker.isRunning():
            return
        if not self._check_deps():
            return
        self._set_status("正在加载正文…")
        self._article_worker = ArticleFetchWorker(url)
        self._article_worker.succeeded.connect(self._on_article_succeeded)
        self._article_worker.failed.connect(self._on_article_failed)
        self._article_worker.finished.connect(self._on_article_finished)
        self._article_worker.start()

    def _check_deps(self) -> bool:
        """检查网络抓取依赖是否可用；缺失时提示安装并返回 False。"""
        try:
            import bs4  # noqa: F401
            import requests  # noqa: F401
            return True
        except ImportError:
            self._set_status(
                "缺少网络依赖 requests / beautifulsoup4，"
                "请运行 setup.bat 或 pip install -r requirements.txt 后重试"
            )
            return False

    def _on_article_succeeded(self, url: str, content: str) -> None:
        if self._selected and self._selected.url == url:
            self._selected.content = content
            self._render_detail(self._selected)
            self._save_item_content(self._selected)
        self._set_status("正文加载完成")

    def _on_article_failed(self, url: str, message: str) -> None:
        if self._selected and self._selected.url == url:
            hint = (
                "正文抓取失败，可点击「阅读原文」在浏览器中查看。\n\n"
                f"原因：{message}"
            )
            self.content_view.setPlainText(hint)
        self._set_status("正文加载失败")

    def _on_article_finished(self) -> None:
        if self._article_worker:
            self._article_worker.deleteLater()
        self._article_worker = None

    def _save_item_content(self, item: NewsItem) -> None:
        """将抓到的正文写回当日缓存。"""
        cached = self._cache.get_day(self._current_date)
        for cached_item in cached:
            if cached_item.url == item.url:
                cached_item.content = item.content
                break
        self._cache.set_day(self._current_date, cached)

    # ================================================================
    # 操作
    # ================================================================

    def _on_open_browser(self) -> None:
        if self._selected and self._selected.url:
            QDesktopServices.openUrl(QUrl(self._selected.url))

    def _on_toggle_favorite(self) -> None:
        if not self._selected:
            return
        now_fav = self._cache.toggle_favorite(self._selected)
        self.btn_fav.setText("★ 已收藏" if now_fav else "☆ 收藏")
        self._set_status("已收藏" if now_fav else "已取消收藏")
        self._apply_filters()

    def _on_export(self) -> None:
        if not self._displayed_items:
            self._set_status("当前没有可导出的内容")
            return
        default_name = f"每日时政_{self._current_date}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出每日时政", default_name, "文本文件 (*.txt)"
        )
        if not path:
            return
        try:
            self._cache.export_txt(self._current_date, self._displayed_items, path)
            show_success(self, "导出成功", f"已导出 {len(self._displayed_items)} 条时政到：\n{path}")
            self._set_status(f"已导出：{path}")
        except Exception as exc:
            self._set_status(f"导出失败：{exc}")

    def _set_status(self, message: str) -> None:
        self.lbl_status.setText(message)
        self.status_message.emit(message)


def _error_source(message: str) -> str:
    """从抓取错误消息中提取来源名（消息以「来源名 请求失败/…」开头）。"""
    return message.split(" ")[0] if message else "未知"
