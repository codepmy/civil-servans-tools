"""后台转换工作线程: 在QThread中执行PDF转换，避免阻塞UI。"""

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from tools.pdf_converter.core.pipeline import ConversionPipeline


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


class BatchConversionWorker(QThread):
    """批量PDF转换线程：串行转换多个文件，复用同一个 Pipeline。

    Pipeline 必须在主线程创建（ReportLab 字体注册需要主线程），
    然后传入本 Worker 在后台线程中调用 run()。

    Signals:
        overall_progress: 整体进度 (current: int, total: int, filename: str)
        file_done: 单文件完成 (filename: str, pdf_bytes: bytes)
        file_failed: 单文件失败 (filename: str, error: str)
        all_finished: 全部结束
    """
    overall_progress = pyqtSignal(int, int, str)
    file_done = pyqtSignal(str, bytes)
    file_failed = pyqtSignal(str, str)
    all_finished = pyqtSignal()

    def __init__(self, pipeline: ConversionPipeline, file_paths: list[str],
                 template_name: str = "xingce",
                 config_overrides: dict | None = None):
        super().__init__()
        self._pipeline = pipeline
        self.file_paths = file_paths
        self.template_name = template_name
        self.config_overrides = config_overrides or {}

    def run(self):
        total = len(self.file_paths)
        for idx, path in enumerate(self.file_paths):
            if self.isInterruptionRequested():
                break
            filename = Path(path).name
            self.overall_progress.emit(idx + 1, total, filename)
            try:
                pdf_bytes = self._pipeline.run(
                    path,
                    template_name=self.template_name,
                    config_overrides=self.config_overrides,
                )
                self.file_done.emit(filename, pdf_bytes)
            except BaseException as e:
                import traceback
                detail = traceback.format_exc()
                self.file_failed.emit(filename, f"{e}\n\n详细:\n{detail[-2000:]}")
        self.all_finished.emit()
