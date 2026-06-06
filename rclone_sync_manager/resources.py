from __future__ import annotations

from importlib import resources
from pathlib import Path


def app_icon_path() -> Path:
    packaged = resources.files("rclone_sync_manager").joinpath("assets/rclone-sync-manager.svg")
    if packaged.is_file():
        return Path(str(packaged))
    return Path(__file__).resolve().parent.parent / "assets" / "rclone-sync-manager.svg"
