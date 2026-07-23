"""Small setup-time environment checks for CivilServantsTools."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys

# Suppress PaddlePaddle INFO noise during import (the "Could not find
# files for the given pattern(s)" message is harmless but alarms users).
os.environ.setdefault("GLOG_minloglevel", "2")
logging.getLogger("paddle").setLevel(logging.WARNING)
logging.getLogger("paddlex").setLevel(logging.WARNING)


def has_nvidia_gpu() -> bool:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        result = subprocess.run(
            [nvidia_smi],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except Exception:
        return False
    return result.returncode == 0


def check_python() -> int:
    print("python exe:", sys.executable)
    print("python version:", sys.version.replace("\n", " "))
    if sys.version_info < (3, 10):
        print("[ERROR] Python 3.10+ is required.")
        return 1
    if sys.version_info >= (3, 13):
        print("[WARN] Python 3.13 detected. PaddlePaddle wheels may be unavailable.")
        print("       Install Python 3.12 x64 for GPU OCR if CUDA setup fails.")
    return 0


def check_paddle_cuda(required: bool) -> int:
    """Verify PaddlePaddle is installed and check CUDA status."""
    try:
        import paddle
    except ImportError as exc:
        print("[ERROR] PaddlePaddle is not installed:", exc)
        return 1 if required else 0

    gpu_compiled = paddle.is_compiled_with_cuda()
    device_count = paddle.device.cuda.device_count() if gpu_compiled else 0
    device = (
        paddle.device.cuda.get_device_name(0)
        if gpu_compiled and device_count > 0
        else "CPU"
    )
    print("paddle version:", paddle.__version__)
    print("cuda compiled:", gpu_compiled)
    print("gpu count:", device_count)
    print("device:", device)

    if required and not gpu_compiled:
        print(
            "[ERROR] NVIDIA GPU detected, but PaddlePaddle CUDA is not available."
        )
        return 1
    return 0


def check_ocr() -> int:
    missing = []
    for module_name in ("paddle", "paddleocr"):
        try:
            __import__(module_name)
        except ImportError as exc:
            missing.append(f"{module_name}: {exc}")
    if missing:
        print("[ERROR] OCR dependencies are missing.")
        for item in missing:
            print(" -", item)
        return 1
    print("OCR dependencies: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", action="store_true")
    parser.add_argument("--cuda", action="store_true")
    parser.add_argument("--cuda-required", action="store_true")
    parser.add_argument("--paddle-cuda", action="store_true")
    parser.add_argument("--paddle-cuda-required", action="store_true")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--nvidia", action="store_true")
    args = parser.parse_args()

    if args.python:
        return check_python()
    if args.cuda or args.cuda_required:
        return check_paddle_cuda(required=args.cuda_required)
    if args.paddle_cuda:
        return check_paddle_cuda(required=False)
    if args.paddle_cuda_required:
        return check_paddle_cuda(required=True)
    if args.ocr:
        return check_ocr()
    if args.nvidia:
        print("nvidia gpu:", has_nvidia_gpu())
        return 0 if has_nvidia_gpu() else 1
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
