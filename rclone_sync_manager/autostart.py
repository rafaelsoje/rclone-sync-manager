from __future__ import annotations

import sys
from pathlib import Path

from .platform_utils import is_windows, windows_startup_dir


DESKTOP_FILE_NAME = "rclone-sync-manager.desktop"
WINDOWS_AUTOSTART_FILE_NAME = "rclone-sync-manager.bat"


def autostart_dir() -> Path:
    if is_windows():
        return windows_startup_dir()
    return Path.home() / ".config" / "autostart"


def autostart_file_path() -> Path:
    if is_windows():
        return autostart_dir() / WINDOWS_AUTOSTART_FILE_NAME
    return autostart_dir() / DESKTOP_FILE_NAME


def is_desktop_autostart_enabled() -> bool:
    return autostart_file_path().exists()


def set_desktop_autostart(enabled: bool) -> Path:
    path = autostart_file_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = windows_batch_content(sys.executable) if is_windows() else desktop_file_content(sys.executable)
        path.write_text(content, encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return path


def desktop_file_content(python_executable: str) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Rclone Sync Manager
Comment=Start Rclone Sync Manager tray at login
Exec={_desktop_exec_quote(python_executable)} -m rclone_sync_manager gui --start-hidden
Terminal=false
X-GNOME-Autostart-enabled=true
"""


def windows_batch_content(python_executable: str) -> str:
    return (
        "@echo off\n"
        f'start "" /min "{python_executable}" -m rclone_sync_manager gui --start-hidden\n'
    )


def _desktop_exec_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
