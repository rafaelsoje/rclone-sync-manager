from __future__ import annotations

import shutil
import subprocess


def notify(title: str, message: str) -> None:
    if not shutil.which("notify-send"):
        return
    subprocess.run(["notify-send", "-a", "Rclone Sync Manager", "-i", "rclone-sync-manager", title, message], check=False)
