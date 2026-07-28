"""PaddleOCR 2.x recognizer implementation — subprocess-backed.

In PyInstaller bundles, PaddleOCR runs in a **subprocess** that uses the
system Python installation.  This keeps the frozen exe small (~100 MB
instead of ~600 MB) while still allowing OCR when a system Python with
PaddlePaddle / PaddleOCR is available.

The subprocess script is embedded as ``_SUBPROCESS_SCRIPT`` and written
to a temp file on first use.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

# Must be set BEFORE any ``import paddle`` — PaddlePaddle reads these
# environment variables at import time and caches the values.
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from tools.ocr_engine.base import BaseRecognizer, OCRRegion

# ======================================================================
# Embedded OCR subprocess script
# ======================================================================

_SUBPROCESS_SCRIPT = r'''
"""OCR subprocess — invoked by the frozen exe via system Python.

Protocol (stdin/stdout JSON-Lines)::

    ← {"cmd":"detect_gpu"}
    → {"using_gpu":true,"device_label":"GPU: …"}

    ← {"cmd":"warm_up","use_gpu":true,"handwritten":false}
    → {"ok":true}

    ← {"cmd":"recognize","image_path":"C:\\tmp\\ocr.png","use_gpu":true,"handwritten":false}
    → {"regions":[{"text":"…","bbox":[x0,y0,x1,y1],"confidence":0.99}]}

    ← {"cmd":"quit"}          # graceful shutdown
"""

import json
import os
import sys
import traceback
from typing import Any

import numpy as np
from PIL import Image

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# ── shared state (persists across commands) ──────────────────────────
_ocr: Any = None
_ocr_use_gpu = False


def _suppress_paddle_logs():
    """Prevent PaddleOCR/PaddlePaddle from printing download progress etc.
    to stdout, which would corrupt the JSON-Lines protocol."""
    import logging
    import warnings
    os.environ.setdefault("GLOG_minloglevel", "2")
    os.environ.setdefault("DISABLE_MODEL_TEST", "1")
    for _name in ("paddle", "paddleocr", "ppocr", "PaddleX"):
        logging.getLogger(_name).setLevel(logging.ERROR)
    warnings.filterwarnings("ignore")


class _SuppressStdout:
    """Context manager that redirects stdout to a dummy file."""

    def __enter__(self):
        self._old = sys.stdout
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        return self

    def __exit__(self, *args):
        sys.stdout.close()
        sys.stdout = self._old


# ── NumPy compat: PaddlePaddle 2.6.x / scipy reference removed aliases ──
# These were deprecated in NumPy 1.20 and removed in 1.24 / 2.0.
import numpy as _np
for _attr, _replacement in (
    ("long",       _np.int64),
    ("ulong",      _np.uint64),
    ("longlong",   _np.int64),
    ("ulonglong",  _np.uint64),
    ("unicode",    _np.str_),
    ("float_",     _np.float64),
    ("bool_",      _np.bool_),
    ("object_",    _np.object_),
    ("str_",       _np.str_),
):
    if not hasattr(_np, _attr):
        setattr(_np, _attr, _replacement)
# Reconstruct sctypes if missing (NumPy ≥ 2.0).
if not hasattr(_np, "sctypes"):
    _dtypes = {}
    for _key, _dtype_list in _np.sctypeDict.items():
        _type_str = str(_key)
        if not _type_str.startswith("type"):
            continue
        _dt = _dtype_list[0] if isinstance(_dtype_list, tuple) else _dtype_list
        _k = _dt.__name__.lstrip("_")
        _dtypes.setdefault(_k, []).append(_dt)
    _np.sctypes = _dtypes


def _detect_gpu() -> dict:
    import paddle
    try:
        compiled = paddle.is_compiled_with_cuda()
        count = paddle.device.cuda.device_count() if compiled else 0
        if count > 0:
            props = paddle.device.cuda.get_device_properties(0)
            name = props.name
            cc = (props.major, props.minor)
            if cc > (9, 0):
                return {
                    "using_gpu": False,
                    "device_label": (
                        f"CPU（{name} 计算能力 {cc[0]}.{cc[1]} "
                        "不被 PaddlePaddle 2.6.2 支持）"
                    ),
                }
            return {"using_gpu": True, "device_label": f"GPU: {name}"}
    except Exception:
        pass
    return {"using_gpu": False, "device_label": "CPU"}


def _ensure_rgb(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return np.stack([image] * 3, axis=-1)
    if image.ndim == 3 and image.shape[2] == 4:
        return image[:, :, :3]
    if image.ndim == 3 and image.shape[2] == 3:
        return image
    return np.array(Image.fromarray(image).convert("RGB"))


def _get_ocr(use_gpu: bool, handwritten: bool) -> Any:
    """Return a cached PaddleOCR instance, creating one if needed."""
    global _ocr, _ocr_use_gpu
    if _ocr is not None and _ocr_use_gpu == use_gpu:
        return _ocr

    from paddleocr import PaddleOCR

    kwargs: dict = {"lang": "ch", "use_gpu": use_gpu}
    if handwritten:
        kwargs.update({
            "det_db_thresh": 0.3,
            "det_db_box_thresh": 0.4,
            "drop_score": 0.3,
            "use_space_char": True,
        })

    _ocr = PaddleOCR(**kwargs)
    _ocr_use_gpu = use_gpu
    return _ocr


def cmd_recognize(req: dict) -> dict:
    image_path = req["image_path"]
    use_gpu = req.get("use_gpu", False)
    handwritten = req.get("handwritten", False)

    img = Image.open(image_path)
    rgb = _ensure_rgb(np.array(img))

    with _SuppressStdout():
        ocr = _get_ocr(use_gpu, handwritten)
        result = ocr.ocr(rgb)

    regions: list[dict] = []
    if result and result[0]:
        for det in result[0]:
            bbox_points, (text, confidence) = det
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            regions.append({
                "text": text,
                "bbox": [min(xs), min(ys), max(xs), max(ys)],
                "confidence": float(confidence),
            })
    return {"regions": regions}


def main() -> None:
    _suppress_paddle_logs()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        cmd = req.get("cmd", "")
        resp: dict[str, Any] = {}

        try:
            if cmd == "quit":
                break
            elif cmd == "detect_gpu":
                resp = _detect_gpu()
            elif cmd == "warm_up":
                with _SuppressStdout():
                    _get_ocr(req.get("use_gpu", False), req.get("handwritten", False))
                resp = {"ok": True}
            elif cmd == "recognize":
                resp = cmd_recognize(req)
            else:
                resp = {"ok": False, "error": f"Unknown command: {cmd}"}
        except Exception:
            resp = {"ok": False, "error": traceback.format_exc()}

        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
'''

# ======================================================================
# Helpers (main process)
# ======================================================================

_cached_system_python: str | None = None


def _find_system_python() -> str | None:
    """Return path to a system Python executable, or *None*."""
    global _cached_system_python
    if _cached_system_python is not None:
        return _cached_system_python

    for cmd in ("python", "python3"):
        try:
            result = subprocess.run(
                [cmd, "-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                exe = result.stdout.strip()
                if exe and os.path.isfile(exe):
                    _cached_system_python = exe
                    return exe
        except Exception:
            continue
    return None


# ======================================================================
# PaddleRecognizer
# ======================================================================


class PaddleRecognizer(BaseRecognizer):
    """OCR engine backed by PaddleOCR 2.x + PaddlePaddle 2.x.

    In PyInstaller bundles the engine runs in a **subprocess** that uses
    the system Python so the frozen exe stays small (~100 MB).

    Parameters:
        handwritten:
            When *True* the engine lowers detection thresholds to capture
            more candidate regions – useful for handwriting.
    """

    _MODEL_DIR = Path.home() / ".paddleocr"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, handwritten: bool = False) -> None:
        self._handwritten = bool(handwritten)
        self._proc: subprocess.Popen | None = None
        self._script_path: str | None = None
        self._using_gpu = False
        self._device_label = "CPU"
        self._closed = False

    # ── subprocess management ────────────────────────────────────────

    def _ensure_subprocess(self) -> None:
        """Start the persistent OCR subprocess (idempotent)."""
        if self._closed:
            raise RuntimeError("PaddleRecognizer has been closed")
        if self._proc is not None:
            return

        python_exe = _find_system_python()
        if not python_exe:
            raise RuntimeError(
                "未找到系统 Python 环境。\n\n"
                "OCR 功能需要系统安装 Python 3.10–3.12 以及 "
                "PaddlePaddle / PaddleOCR。"
            )

        # Write the embedded script to a temp file.
        fd, self._script_path = tempfile.mkstemp(
            suffix=".py", prefix="ocr_worker_"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_SUBPROCESS_SCRIPT)

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            self._proc = subprocess.Popen(
                [python_exe, self._script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                env=env,
            )
        except Exception:
            self._cleanup_script()
            raise

        # ── probe GPU ──────────────────────────────────────────────
        try:
            info = self._send_cmd({"cmd": "detect_gpu"})
            self._using_gpu = bool(info.get("using_gpu", False))
            self._device_label = str(info.get("device_label", "CPU"))
        except Exception:
            self._using_gpu = False
            self._device_label = "CPU"

    def _send_cmd(self, cmd_dict: dict) -> dict:
        """Send one JSON command to the subprocess and return the response."""
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

        payload = json.dumps(cmd_dict, ensure_ascii=False) + "\n"
        self._proc.stdin.write(payload)
        self._proc.stdin.flush()

        line = self._proc.stdout.readline()
        if not line:
            self._proc.wait(timeout=1)
            raise RuntimeError(
                "OCR 子进程意外退出，请检查系统 Python 环境是否安装了 "
                "PaddlePaddle / PaddleOCR。"
            )

        try:
            resp = json.loads(line)
        except json.JSONDecodeError:
            raise RuntimeError(f"OCR 子进程返回无效数据: {line[:200]}")

        if resp.get("error"):
            raise RuntimeError(f"OCR 子进程错误:\n{resp['error'][-500:]}")

        return resp

    def _cleanup_script(self) -> None:
        if self._script_path:
            try:
                os.unlink(self._script_path)
            except OSError:
                pass
            self._script_path = None

    def close(self) -> None:
        """Shut down the OCR subprocess and release temp files."""
        if self._closed:
            return
        self._closed = True

        if self._proc:
            try:
                self._proc.stdin.write('{"cmd":"quit"}\n')
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        self._cleanup_script()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # BaseRecognizer properties
    # ------------------------------------------------------------------

    @property
    def device_label(self) -> str:
        return self._device_label

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu

    # ------------------------------------------------------------------
    # Class-level checks
    # ------------------------------------------------------------------

    @classmethod
    def is_first_time(cls) -> bool:
        """Model cache is empty → PaddleOCR will download on first use."""
        return (
            not cls._MODEL_DIR.exists()
            or not any(cls._MODEL_DIR.iterdir())
        )

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        """Return ``(True, "")`` if a system Python with PaddleOCR is reachable.

        Uses a one-shot subprocess — does not start the persistent worker.
        """
        python_exe = _find_system_python()
        if not python_exe:
            return (
                False,
                "未找到系统 Python 环境。\n\n"
                "OCR 功能需要系统安装 Python 3.10–3.12。",
            )

        try:
            result = subprocess.run(
                [python_exe, "-c",
                 # Restore NumPy type aliases removed in 1.24/2.0
                 # so older PaddlePaddle & scipy can import.
                 "import numpy as _n;"
                 "[setattr(_n,a,v) for a,v in ["
                 "('long',_n.int64),('ulong',_n.uint64),"
                 "('longlong',_n.int64),('ulonglong',_n.uint64),"
                 "('unicode',_n.str_),('float_',_n.float64),"
                 "('bool_',_n.bool_),('object_',_n.object_),"
                 "('str_',_n.str_),"
                 "] if not hasattr(_n,a)];"
                 "import paddle; from paddleocr import PaddleOCR"],
                capture_output=True, text=True, timeout=60,
            )
        except Exception as exc:
            return (
                False,
                f"无法调用系统 Python ({python_exe})。\n\n"
                f"原始错误: {exc}",
            )

        if result.returncode != 0:
            detail = (result.stderr + result.stdout).strip()
            # Detect common issues.
            if "np.sctypes" in detail or "was removed in the NumPy" in detail:
                hint = (
                    "检测到 NumPy 版本不兼容（NumPy ≥ 2.0 移除了 PaddlePaddle 依赖的 "
                    "``np.sctypes``）。\n\n"
                    "请在命令行执行以下命令降级 NumPy：\n"
                    "    pip install \"numpy<2.0\"\n\n"
                    "降级后重新启动本程序即可。"
                )
            elif "No module named" in detail or "ModuleNotFoundError" in detail:
                hint = (
                    "当前环境未安装 OCR 依赖（PaddleOCR / PaddlePaddle）。\n\n"
                    "请点击菜单栏「📦 安装依赖」自动安装，\n"
                    "安装完成后重新启动本程序即可使用 OCR 功能。"
                )
            else:
                hint = (
                    "OCR 环境初始化失败。请确认已安装 PaddlePaddle / PaddleOCR。\n\n"
                    "可点击菜单栏「📦 安装依赖」完成安装。"
                )
            return (False, f"{hint}\n\n── 系统 Python: {python_exe}\n── 原始错误:\n{detail[-800:]}")
        return True, ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def warm_up(self) -> None:
        """Pre-load the PaddleOCR model in the subprocess."""
        self._ensure_subprocess()
        self._send_cmd({
            "cmd": "warm_up",
            "use_gpu": self._using_gpu,
            "handwritten": self._handwritten,
        })

    def recognize(self, image: np.ndarray) -> list[OCRRegion]:
        """Run OCR on a single image (uint8 ndarray, any channel count).

        The image is saved to a temporary PNG, processed in the
        subprocess, and results are parsed back into :class:`OCRRegion`.
        """
        self._ensure_subprocess()

        # Save image → temp PNG.
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="ocr_img_")
        try:
            pil = PILImage.fromarray(_ensure_rgb(image))
            pil.save(tmp_path, format="PNG")

            resp = self._send_cmd({
                "cmd": "recognize",
                "image_path": tmp_path,
                "use_gpu": self._using_gpu,
                "handwritten": self._handwritten,
            })
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        regions_data: list[dict] = resp.get("regions", [])
        return [
            OCRRegion(
                text=r["text"],
                bbox=tuple(r["bbox"]),  # type: ignore[arg-type]
                confidence=r["confidence"],
            )
            for r in regions_data
        ]

    def recognize_batch(
        self, images: list[np.ndarray]
    ) -> list[list[OCRRegion]]:
        return [self.recognize(img) for img in images]


# ======================================================================
# Helpers (main process — image pre-processing)
# ======================================================================


def _ensure_rgb(image: np.ndarray) -> np.ndarray:
    """Return a uint8 RGB copy of *image* regardless of input channels."""
    if image.ndim == 2:
        return np.stack([image] * 3, axis=-1)
    if image.ndim == 3 and image.shape[2] == 4:
        return image[:, :, :3]
    if image.ndim == 3 and image.shape[2] == 3:
        return image
    return np.array(PILImage.fromarray(image).convert("RGB"))
