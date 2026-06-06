from __future__ import annotations

import subprocess
import shutil
from dataclasses import dataclass

from .platform_utils import is_windows


@dataclass(slots=True)
class RemoteEntry:
    name: str
    path: str
    is_dir: bool


@dataclass(slots=True)
class RemoteListResult:
    entries: list[RemoteEntry]
    error: str | None = None


def remote_name(remote_path: str) -> str | None:
    if ":" not in remote_path:
        return None
    name = remote_path.split(":", 1)[0].strip()
    return name or None


def list_remotes(rclone_path: str = "rclone") -> list[str]:
    try:
        completed = subprocess.run(
            [rclone_path, "listremotes"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    return [line.strip().rstrip(":") for line in completed.stdout.splitlines() if line.strip()]


def delete_remote(remote: str, rclone_path: str = "rclone") -> tuple[bool, str]:
    name = remote.strip().rstrip(":")
    if not name:
        return False, "Remote inválido."
    try:
        completed = subprocess.run(
            [rclone_path, "config", "delete", f"{name}:"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def open_rclone_config_terminal(rclone_path: str = "rclone") -> tuple[bool, str]:
    terminal_command = _terminal_command([rclone_path, "config"])
    if terminal_command is None:
        return False, f"Nenhum terminal encontrado. Rode manualmente: {rclone_path} config"
    try:
        _popen_terminal(terminal_command)
    except OSError as exc:
        return False, str(exc)
    return True, ""


def _popen_terminal(command: list[str]) -> subprocess.Popen:
    kwargs = {}
    if is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen(command, **kwargs)


def _terminal_command(command: list[str]) -> list[str] | None:
    if is_windows():
        return ["cmd.exe", "/k", subprocess.list2cmdline(command)]
    joined = " ".join(_shell_quote(part) for part in command)
    candidates = [
        ("konsole", ["konsole", "-e", *command]),
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", joined]),
        ("gnome-terminal", ["gnome-terminal", "--", *command]),
        ("xfce4-terminal", ["xfce4-terminal", "-e", joined]),
        ("xterm", ["xterm", "-e", joined]),
    ]
    for executable, terminal_command in candidates:
        if shutil.which(executable):
            return terminal_command
    return None


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def remote_exists(remote_path: str, rclone_path: str = "rclone") -> bool:
    name = remote_name(remote_path)
    if not name:
        return False
    return name in list_remotes(rclone_path)


def split_remote_path(remote_path: str) -> tuple[str, str]:
    if ":" not in remote_path:
        return "", ""
    remote, path = remote_path.split(":", 1)
    return remote.strip(), path.strip("/")


def join_remote_path(remote: str, path: str = "") -> str:
    clean_remote = remote.rstrip(":")
    clean_path = path.strip("/")
    return f"{clean_remote}:{clean_path}" if clean_path else f"{clean_remote}:"


def list_remote_entries(remote_path: str, rclone_path: str = "rclone") -> list[RemoteEntry]:
    return list_remote_entries_result(remote_path, rclone_path).entries


def list_remote_entries_result(remote_path: str, rclone_path: str = "rclone") -> RemoteListResult:
    try:
        completed = subprocess.run(
            [rclone_path, "lsf", remote_path],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return RemoteListResult([], "Não foi possível executar rclone lsf.")
    if completed.returncode != 0:
        return RemoteListResult([], (completed.stderr or completed.stdout).strip() or "Erro ao listar remote.")
    remote, base_path = split_remote_path(remote_path)
    entries: list[RemoteEntry] = []
    for raw_line in completed.stdout.splitlines():
        if not raw_line:
            continue
        is_dir = raw_line.endswith("/")
        name = raw_line.rstrip("/")
        child_path = "/".join(part for part in (base_path, name) if part)
        entries.append(RemoteEntry(name=name, path=join_remote_path(remote, child_path), is_dir=is_dir))
    entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))
    return RemoteListResult(entries)
