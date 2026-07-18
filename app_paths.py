"""Runtime path helpers for source and PyInstaller builds."""

from pathlib import Path
import sys


def app_root() -> Path:
    """Return the directory that contains bundled application data."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass)
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """Build an absolute path to a project resource."""
    return app_root().joinpath(*parts)


def user_config_path() -> Path:
    """Return path to the user configuration file (writable).

    Uses %APPDATA% on Windows (always writable, survives reinstalls).
    Falls back to app root in development.
    """
    if getattr(sys, "frozen", False):
        import os
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            config_dir = Path(appdata) / "CivilServantsTools"
        else:
            config_dir = Path.home() / ".civil_servants_tools"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "user_config.json"
    return app_root() / "user_config.json"
