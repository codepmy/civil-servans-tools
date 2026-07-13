"""Runtime path helpers for source and PyInstaller builds."""

from pathlib import Path
import sys


def app_root() -> Path:
    """Return the directory that contains bundled application data."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """Build an absolute path to a project resource."""
    return app_root().joinpath(*parts)
