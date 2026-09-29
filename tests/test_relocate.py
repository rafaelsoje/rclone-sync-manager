from __future__ import annotations

from pathlib import Path
import pytest

from rclone_sync_manager.database import Database
from rclone_sync_manager.models import Job
from rclone_sync_manager.relocate import relocate_job_path


def test_relocate_same_path(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    local_dir = tmp_path / "docs"
    local_dir.mkdir()

    job = db.create_job(Job(name="Docs", local_path=str(local_dir), remote_path="drive:Docs"))
    ok, msg = relocate_job_path(db, job, local_dir, move_files=True)
    assert ok
    assert "idênticos" in msg


def test_relocate_subpath_error(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    local_dir = tmp_path / "parent"
    local_dir.mkdir()

    job = db.create_job(Job(name="Parent", local_path=str(local_dir), remote_path="drive:Parent"))
    with pytest.raises(ValueError, match="subpasta"):
        relocate_job_path(db, job, local_dir / "child")


def test_relocate_moves_files_and_updates_db(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    old_dir = tmp_path / "old_location"
    old_dir.mkdir()
    (old_dir / "file1.txt").write_text("hello", encoding="utf-8")
    (old_dir / "subdir").mkdir()
    (old_dir / "subdir" / "file2.txt").write_text("world", encoding="utf-8")

    job = db.create_job(Job(name="MoveTest", local_path=str(old_dir), remote_path="drive:MoveTest", mode="bisync"))
    db.set_setting(f"bisync_initialized:{job.id}", "true")

    new_dir = tmp_path / "new_location"
    ok, msg = relocate_job_path(db, job, new_dir, move_files=True, resync_bisync=False)

    assert ok
    assert not old_dir.exists()
    assert (new_dir / "file1.txt").read_text(encoding="utf-8") == "hello"
    assert (new_dir / "subdir" / "file2.txt").read_text(encoding="utf-8") == "world"

    updated = db.get_job("MoveTest")
    assert updated.local_path == str(new_dir)
    assert db.get_setting(f"bisync_initialized:{job.id}") == "false"


def test_relocate_without_move(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    old_dir = tmp_path / "keep_old"
    old_dir.mkdir()
    (old_dir / "stay.txt").write_text("stay", encoding="utf-8")

    job = db.create_job(Job(name="NoMove", local_path=str(old_dir), remote_path="drive:NoMove"))
    new_dir = tmp_path / "empty_new"

    ok, msg = relocate_job_path(db, job, new_dir, move_files=False, resync_bisync=False)
    assert ok
    assert (old_dir / "stay.txt").exists()
    assert new_dir.exists()
    assert not any(new_dir.iterdir())
