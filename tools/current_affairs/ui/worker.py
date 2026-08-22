"""时政新闻后台工作线程。"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from tools.current_affairs.core.fetcher import NewsFetcher
from tools.current_affairs.core.reader import fetch_article_text


class FetchWorker(QThread):
    """后台抓取当日时政（多源聚合）。"""

    progress = pyqtSignal(str)
    succeeded = pyqtSignal(object)  # dict: {date, items, errors, sources_ok, sources_total}
    failed = pyqtSignal(str)

    def __init__(self, date_str: str, parent=None):
        super().__init__(parent)
        self._date = date_str

    def run(self) -> None:
        try:
            self.progress.emit("正在抓取最新时政（政府网/新华网/人民网）…")
            result = NewsFetcher().fetch_all()
            self.succeeded.emit(
                {
                    "date": self._date,
                    "items": result.items,
                    "errors": result.errors,
                    "sources_ok": result.sources_ok,
                    "sources_total": result.sources_total,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class ArticleFetchWorker(QThread):
    """后台抓取单条新闻正文。"""

    succeeded = pyqtSignal(str, str)  # url, content
    failed = pyqtSignal(str, str)     # url, message

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            content = fetch_article_text(self._url)
            self.succeeded.emit(self._url, content)
        except Exception as exc:
            self.failed.emit(self._url, str(exc))
