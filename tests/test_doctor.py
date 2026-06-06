from pathlib import Path

from rclone_sync_manager.database import Database
from rclone_sync_manager.doctor import DoctorCheck, has_failures, run_checks


def test_has_failures() -> None:
    assert not has_failures([DoctorCheck("ok", True)])
    assert has_failures([DoctorCheck("bad", False)])


def test_run_checks_includes_sqlite(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()

    checks = run_checks(db)

    assert any(check.name == "sqlite" and check.ok for check in checks)
