from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from .database import Database
from .platform_utils import is_linux, is_windows
from .systemd import service_status


@dataclass(slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str = ""


def run_checks(db: Database) -> list[DoctorCheck]:
    checks = [
        DoctorCheck("rclone", shutil.which("rclone") is not None, shutil.which("rclone") or "nao encontrado"),
        DoctorCheck("watchdog import", _can_import("watchdog"), "modulo Python watchdog"),
        DoctorCheck("PySide6 import", _can_import("PySide6"), "modulo Python PySide6"),
        _linux_tool_check("systemctl", required=is_linux()),
        _linux_tool_check("ionice", required=is_linux()),
        _linux_tool_check("nice", required=is_linux()),
        _linux_tool_check("notify-send", required=False),
        _sqlite_check(db),
        _systemd_service_check(),
        _rclone_remotes_check(),
    ]
    return checks


def has_failures(checks: list[DoctorCheck]) -> bool:
    return any(not check.ok for check in checks)


def _can_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def _linux_tool_check(name: str, *, required: bool) -> DoctorCheck:
    path = shutil.which(name)
    if path:
        return DoctorCheck(name, True, path)
    if required:
        return DoctorCheck(name, False, "nao encontrado")
    detail = "nao aplicavel no Windows" if is_windows() else "opcional"
    return DoctorCheck(name, True, detail)


def _sqlite_check(db: Database) -> DoctorCheck:
    try:
        db.initialize()
        db.list_jobs()
    except Exception as exc:
        return DoctorCheck("sqlite", False, str(exc))
    return DoctorCheck("sqlite", True, str(db.db_path))


def _systemd_service_check() -> DoctorCheck:
    if not is_linux():
        return DoctorCheck("systemd user service", True, "nao aplicavel no Windows")
    result = service_status()
    output = result.output or "sem saida"
    return DoctorCheck("systemd user service", result.ok, output)


def _rclone_remotes_check() -> DoctorCheck:
    if not shutil.which("rclone"):
        return DoctorCheck("rclone remotes", False, "rclone nao encontrado")
    try:
        completed = subprocess.run(
            ["rclone", "listremotes"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DoctorCheck("rclone remotes", False, str(exc))
    remotes = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0:
        return DoctorCheck("rclone remotes", False, completed.stderr.strip())
    if not remotes:
        return DoctorCheck("rclone remotes", False, "nenhum remote configurado")
    return DoctorCheck("rclone remotes", True, ", ".join(remotes))
