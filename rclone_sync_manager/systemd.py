from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import APP_NAME
from .platform_utils import is_linux


SERVICE_NAME = "rclone-sync-manager.service"


@dataclass(slots=True)
class CommandResult:
    ok: bool
    output: str


def user_service_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def installed_service_path() -> Path:
    return user_service_dir() / SERVICE_NAME


def is_systemctl_available() -> bool:
    return is_linux() and shutil.which("systemctl") is not None


def install_service_file(source: Path | None = None) -> Path:
    destination = installed_service_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source is not None:
        content = source.read_text(encoding="utf-8")
    else:
        content = service_file_content(sys.executable)
    destination.write_text(content, encoding="utf-8")
    return destination


def service_file_content(python_executable: str) -> str:
    return f"""[Unit]
Description=Rclone Sync Manager
After=network-online.target

[Service]
Type=simple
ExecStart={_systemd_quote(python_executable)} -m rclone_sync_manager start
Restart=always
RestartSec=10
Nice=19
IOSchedulingClass=idle

[Install]
WantedBy=default.target
"""


def set_autostart(enabled: bool) -> CommandResult:
    if not is_linux():
        return CommandResult(False, "servico systemd disponivel apenas no Linux")
    if not is_systemctl_available():
        return CommandResult(False, "systemctl não encontrado")
    install_service_file()
    daemon_reload = _run(["systemctl", "--user", "daemon-reload"])
    if not daemon_reload.ok:
        return daemon_reload
    command = ["systemctl", "--user", "enable", "--now", SERVICE_NAME]
    if not enabled:
        command = ["systemctl", "--user", "disable", "--now", SERVICE_NAME]
    return _run(command)


def service_status() -> CommandResult:
    if not is_linux():
        return CommandResult(False, "servico systemd disponivel apenas no Linux")
    if not is_systemctl_available():
        return CommandResult(False, "systemctl não encontrado")
    return _run(["systemctl", "--user", "is-active", SERVICE_NAME])


def is_service_active() -> bool:
    return service_status().output.strip() == "active"


def _systemd_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _run(command: list[str]) -> CommandResult:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(False, str(exc))
    output = (completed.stdout + completed.stderr).strip()
    return CommandResult(completed.returncode == 0, output)
