from __future__ import annotations

import os
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def config_home() -> Path:
    if "XDG_CONFIG_HOME" in os.environ:
        return Path(os.environ["XDG_CONFIG_HOME"]).expanduser()
    if is_windows() and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]).expanduser()
    return Path.home() / ".config"


def data_home() -> Path:
    if "XDG_DATA_HOME" in os.environ:
        return Path(os.environ["XDG_DATA_HOME"]).expanduser()
    if is_windows() and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]).expanduser()
    return Path.home() / ".local" / "share"


def windows_startup_dir() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")).expanduser()
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
