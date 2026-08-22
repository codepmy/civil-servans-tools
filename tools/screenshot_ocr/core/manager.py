"""截图 OCR 流程编排器。

串联 热键 → 截图 → OCR → 剪贴板 全流程，管理 PaddleRecognizer
单例生命周期与用户配置读写。
"""

from __future__ import annotations

import json
import threading
import traceback
from typing import Any

import numpy as np
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from app_paths import user_config_path
from tools.screenshot_ocr.core.hotkey_manager import HotkeyManager
from tools.screenshot_ocr.ui.overlay import ScreenshotOverlay
from tools.screenshot_ocr.ui.toast import Toast
from tools.screenshot_ocr.worker import ScreenshotOCRWorker

_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "hotkey": {
        "modifiers": ["ctrl", "shift"],
        "key":       "Z",
        "key_code":  90,
    },
}

# OCR 引擎预热相关常量
_WARMUP_DELAY_MS = 3000     # 启动后延迟多久开始预热（避开程序启动资源高峰）
_WARMUP_WAIT_S = 90         # 截图时等待预热完成的上限（首次冷加载模型约 10-30s）
# 预热状态: idle(未开始) → warming(进行中) → ready | failed
_ENGINE_IDLE, _ENGINE_WARMING, _ENGINE_READY, _ENGINE_FAILED = (
    "idle", "warming", "ready", "failed"
)


class ScreenshotOCRManager(QObject):
    """截图 OCR 流程编排器。"""

    status_message = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = QApplication.instance()
        self._hotkey_mgr = HotkeyManager()
        self._hotkey_mgr.registration_result.connect(self._on_registration_result)
        self._engine = None
        self._overlay: ScreenshotOverlay | None = None
        self._worker: ScreenshotOCRWorker | None = None
        # 引擎预热状态机（threading.Condition 保护，预热线程与主线程共享）
        self._engine_cond = threading.Condition()
        self._engine_state = _ENGINE_IDLE
        self._warmup_thread: threading.Thread | None = None

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """启动管理器：加载配置 → 启动热键轮询。"""
        config = self._load_config()
        mod_list = config["hotkey"]["modifiers"]
        key = config["hotkey"]["key"]

        self._hotkey_mgr.hotkey_triggered.connect(self._on_hotkey)
        self._hotkey_mgr.start(mod_list, key)

        # 延迟后台预热 OCR 引擎，避免首次截图时冷启动卡顿
        QTimer.singleShot(_WARMUP_DELAY_MS, self._start_warmup)

    def shutdown(self) -> None:
        """关闭管理器：停止轮询 + 清理 OCR 引擎（含预热中的引擎）。"""
        self._hotkey_mgr.stop()
        engine = None
        with self._engine_cond:
            if self._engine_state == _ENGINE_WARMING:
                # 预热中：短等收尾；未完成则交给 daemon 线程自行释放
                #（其子进程 stdin 断开后自动退出，不阻塞程序退出）
                self._engine_cond.wait(timeout=5)
            engine = self._engine
            self._engine = None
            self._engine_state = _ENGINE_IDLE
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass

    def trigger(self) -> None:
        """手动触发截图 OCR 流程。"""
        self._on_hotkey()

    # ── Hotkey ──────────────────────────────────────────────────────

    def set_hotkey(self, mod_list: list[str], key: str) -> None:
        """更换全局热键并持久化配置。"""
        self._hotkey_mgr.start(mod_list, key)
        self._save_hotkey_config(mod_list, key)
        self.status_message.emit(
            f"快捷键已更新：{'+'.join(mod_list)}+{key}"
        )

    # ── Config queries ─────────────────────────────────────────────

    def current_mod_list(self) -> list[str]:
        return self._hotkey_mgr._mods

    def current_key_name(self) -> str:
        return HotkeyManager.key_from_vk(self._hotkey_mgr.current_vk)

    # ── Internal: flow ──────────────────────────────────────────────

    def _on_registration_result(self, ok: bool, message: str) -> None:
        self.status_message.emit(message)
        if ok:
            Toast.show_message(message, variant="success", duration_ms=4000)
        else:
            Toast.show_message(message, variant="error", duration_ms=6000)

    def _on_hotkey(self) -> None:
        # 有模态弹窗时忽略快捷键，避免截图覆盖层卡死
        if QApplication.activeModalWidget() is not None:
            return
        try:
            self._overlay = ScreenshotOverlay()
            self._overlay.captured.connect(self._on_captured)
            self._overlay.cancelled.connect(self._on_cancelled)
            self._overlay.destroyed.connect(self._on_overlay_destroyed)
            self._overlay.start()
        except Exception:
            Toast.show_message(
                f"截图启动失败：{traceback.format_exc()[-200:]}",
                variant="error",
            )

    def _on_captured(self, image: np.ndarray) -> None:
        self._run_ocr(image)

    def _on_cancelled(self) -> None:
        pass

    def _on_overlay_destroyed(self) -> None:
        self._overlay = None

    def _run_ocr(self, image: np.ndarray) -> None:
        self._worker = ScreenshotOCRWorker(image, engine=self._get_engine())
        self._worker.succeeded.connect(self._on_ocr_succeeded)
        self._worker.failed.connect(self._on_ocr_failed)
        self._worker.start()

    def _on_ocr_succeeded(self, text: str) -> None:
        if text:
            QApplication.clipboard().setText(text)
            lines = text.strip().split("\n")
            line_count = len([l for l in lines if l.strip()])
            Toast.show_message(
                f"已识别 {line_count} 个文字区域，已复制到剪贴板",
                variant="success",
            )
        else:
            Toast.show_message("截图未检测到文字", variant="warning")
        self._cleanup_worker()

    def _on_ocr_failed(self, message: str) -> None:
        if "未找到系统 Python" in message or "ModuleNotFoundError" in message:
            friendly = "OCR 环境未就绪，请点击菜单栏「📦 安装依赖」安装 OCR 引擎"
        elif "CUDNN_MISSING" in message:
            friendly = "缺少 cuDNN 运行时，请安装 cuDNN 8.x"
        else:
            friendly = f"OCR 识别失败：{message[-150:]}"
        Toast.show_message(friendly, variant="error")
        self._cleanup_worker()

    def _cleanup_worker(self) -> None:
        if self._worker:
            try:
                self._worker.deleteLater()
            except Exception:
                pass
            self._worker = None

    # ── Engine singleton ────────────────────────────────────────────

    def _start_warmup(self) -> None:
        """启动后台预热线程（幂等，仅在 idle 时生效）。"""
        with self._engine_cond:
            if self._engine_state != _ENGINE_IDLE:
                return
            self._engine_state = _ENGINE_WARMING
        self._warmup_thread = threading.Thread(
            target=self._warmup_worker, name="socr-warmup", daemon=True
        )
        self._warmup_thread.start()

    def _warmup_worker(self) -> None:
        """预热线程：探测环境 → 拉起 OCR 子进程 → 加载模型。

        全程在后台线程执行（subprocess IO 阻塞，不占用 UI 线程）。
        """
        engine = None
        ok = False
        try:
            from tools.ocr_engine.paddle_recognizer import PaddleRecognizer
            ok, _reason = PaddleRecognizer.is_available()
            if ok:
                engine = PaddleRecognizer(handwritten=False)
                engine.warm_up()
        except Exception:
            ok = False  # 异常视为失败，交给同步兜底给出友好报错

        with self._engine_cond:
            if self._engine_state != _ENGINE_WARMING:
                # 已被同步兜底接管或已 shutdown → 放弃本次预热结果
                if engine is not None:
                    try:
                        engine.close()
                    except Exception:
                        pass
            elif not ok:
                # 预热失败：状态置 failed，首次截图时同步兜底会重试并给出友好报错
                self._engine_state = _ENGINE_FAILED
                if engine is not None:
                    try:
                        engine.close()
                    except Exception:
                        pass
            else:
                self._engine = engine
                self._engine_state = _ENGINE_READY
            self._engine_cond.notify_all()
        self._warmup_thread = None

    def _get_engine(self):
        with self._engine_cond:
            if self._engine_state == _ENGINE_READY:
                return self._engine
            if self._engine_state == _ENGINE_WARMING:
                # 首次冷加载模型约 10-30s，给用户明确提示后等待
                Toast.show_message(
                    "OCR 引擎首次加载中，请稍候…", variant="warning", duration_ms=4000
                )
                self._engine_cond.wait(timeout=_WARMUP_WAIT_S)
                if self._engine_state == _ENGINE_READY:
                    return self._engine
                # 超时或失败 → 置回 idle，走下方同步兜底
                self._engine_state = _ENGINE_IDLE
            elif self._engine_state == _ENGINE_FAILED:
                # 预热失败 → 允许同步重试一次（兜底）
                self._engine_state = _ENGINE_IDLE

        # 同步兜底（与预热前的原逻辑一致）
        from tools.ocr_engine.paddle_recognizer import PaddleRecognizer
        ok, reason = PaddleRecognizer.is_available()
        if not ok:
            raise RuntimeError("OCR 环境未就绪，请先安装依赖。\n\n" + reason)
        engine = PaddleRecognizer(handwritten=False)
        with self._engine_cond:
            self._engine = engine
            self._engine_state = _ENGINE_READY
        return engine

    # ── Config I/O ──────────────────────────────────────────────────

    def _load_config(self) -> dict[str, Any]:
        try:
            path = user_config_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                socr = data.get("screenshot_ocr")
                if isinstance(socr, dict):
                    merged = dict(_DEFAULT_CONFIG)
                    merged.update(socr)
                    if "hotkey" in socr and isinstance(socr["hotkey"], dict):
                        merged["hotkey"] = {**merged["hotkey"], **socr["hotkey"]}
                    return merged
        except Exception:
            pass
        return dict(_DEFAULT_CONFIG)

    def _save_hotkey_config(self, mod_list: list[str], key: str) -> None:
        try:
            path = user_config_path()
            existing: dict[str, Any] = {}
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            existing["screenshot_ocr"] = {
                "enabled": True,
                "hotkey": {
                    "modifiers": mod_list,
                    "key": key,
                    "key_code": HotkeyManager.vk_from_key(key),
                },
            }
            path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
