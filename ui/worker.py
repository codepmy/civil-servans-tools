"""后台转换工作线程: 在QThread中执行PDF转换，避免阻塞UI。"""

from PyQt6.QtCore import QThread, pyqtSignal

from core.pipeline import ConversionPipeline


class ConversionWorker(QThread):
    """后台PDF转换线程。

    Signals:
        progress: 进度更新 (percent: int, stage: str)
        succeeded: 转换完成 (pdf_bytes: bytes)
        failed: 转换出错 (error_message: str)
    """
    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, input_path: str, template_name: str = "xingce",
                 config_overrides: dict | None = None):
        super().__init__()
        self.input_path = input_path
        self.template_name = template_name
        self.config_overrides = config_overrides or {}

    def run(self):
        """在后台线程执行转换。"""
        try:
            pipeline = ConversionPipeline()
            output = pipeline.run(
                self.input_path,
                progress=self._on_progress,
                template_name=self.template_name,
                config_overrides=self.config_overrides,
            )
            self.succeeded.emit(output)
        except BaseException as e:
            import traceback
            detail = traceback.format_exc()
            self.failed.emit(f"{e}\n\n详细:\n{detail[-2000:]}")

    def _on_progress(self, percent: int, stage: str):
        """进度回调(从pipeline线程发出信号)。"""
        if self.isInterruptionRequested():
            raise RuntimeError("用户已取消转换。")
        self.progress.emit(percent, stage)
