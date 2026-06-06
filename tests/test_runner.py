from pathlib import Path

import pytest

from rclone_sync_manager.database import Database
from rclone_sync_manager.models import Job
from rclone_sync_manager.runner import RcloneRunner, _friendly_error_message


def test_build_command_copy_with_limits(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("rclone_sync_manager.runner.is_windows", lambda: False)
    runner = RcloneRunner(db=Database(tmp_path / "rsm.db"), rclone_path="rclone")
    job = Job(
        id=1,
        name="Fotos",
        local_path=str(tmp_path),
        remote_path="gdrive:Fotos",
        mode="copy",
        transfers=4,
        checkers=8,
        bandwidth_limit="2M",
        dry_run=True,
    )

    command, log_file = runner.build_command(job)

    assert command[:5] == ["ionice", "-c3", "nice", "-n", "19"]
    assert "copy" in command
    assert "--bwlimit" in command
    assert "2M" in command
    assert "--stats" in command
    assert "5s" in command
    assert "--dry-run" in command
    assert log_file.name == "Fotos.log"


def test_build_command_omits_unix_priority_tools_on_windows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("rclone_sync_manager.runner.is_windows", lambda: True)
    runner = RcloneRunner(db=Database(tmp_path / "rsm.db"), rclone_path="rclone")
    job = Job(
        id=1,
        name="Fotos",
        local_path=str(tmp_path),
        remote_path="gdrive:Fotos",
        mode="copy",
    )

    command, _ = runner.build_command(job)

    assert command[:4] == ["rclone", "copy", str(tmp_path), "gdrive:Fotos"]


def test_build_command_adds_exclude_patterns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    runner = RcloneRunner(db=Database(tmp_path / "rsm.db"), rclone_path="rclone")
    job = Job(
        id=1,
        name="Fotos",
        local_path=str(tmp_path),
        remote_path="photos:",
        mode="copy",
        ignore_patterns=["upload/**", "*.tmp"],
    )

    command, _ = runner.build_command(job)

    assert command.count("--exclude") == 2
    assert "upload/**" in command
    assert "*.tmp" in command


def test_build_command_adds_include_patterns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    runner = RcloneRunner(db=Database(tmp_path / "rsm.db"), rclone_path="rclone")
    job = Job(
        id=1,
        name="Photos",
        local_path=str(tmp_path),
        remote_path="photos:",
        mode="copy",
        direction="remote_to_local",
        include_patterns=["media/all/**"],
    )

    command, _ = runner.build_command(job)

    assert "--include" in command
    assert "media/all/**" in command
    assert command.count("--exclude") >= 1
    assert "**" in command


def test_build_command_copy_remote_to_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    runner = RcloneRunner(db=Database(tmp_path / "rsm.db"), rclone_path="rclone")
    job = Job(
        id=1,
        name="Restore",
        local_path=str(tmp_path),
        remote_path="dropbox:Restore",
        mode="copy",
        direction="remote_to_local",
        priority_low=False,
    )

    command, _ = runner.build_command(job)

    assert command[:4] == ["rclone", "copy", "dropbox:Restore", str(tmp_path)]


def test_build_command_bisync_resync(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("rclone_sync_manager.runner.is_windows", lambda: False)
    runner = RcloneRunner(db=Database(tmp_path / "rsm.db"), rclone_path="rclone")
    job = Job(
        id=1,
        name="Documentos",
        local_path=str(tmp_path),
        remote_path="gdrive:Documentos",
        mode="bisync",
    )

    command, _ = runner.build_command(job, resync=True)

    assert command[5:9] == ["rclone", "bisync", str(tmp_path), "gdrive:Documentos"]
    assert "--resync" in command


def test_bisync_requires_initialization(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    job = db.create_job(
        Job(
            name="Documentos",
            local_path=str(tmp_path),
            remote_path="gdrive:Documentos",
            mode="bisync",
        )
    )

    runner = RcloneRunner(db=db, rclone_path="rclone")

    with pytest.raises(RuntimeError, match="bisync must be initialized first"):
        runner.run(job)


def test_friendly_error_message_for_missing_directory() -> None:
    message = _friendly_error_message("upload: error reading source directory: directory not found")

    assert message is not None
    assert "Diretório não encontrado" in message
