from pathlib import Path

from rclone_sync_manager.database import Database
from rclone_sync_manager.jobs_io import export_jobs, import_jobs
from rclone_sync_manager.models import Job


def test_export_and_import_jobs(tmp_path: Path) -> None:
    source_db = Database(tmp_path / "source.db")
    source_db.initialize()
    source_db.create_job(
        Job(
            name="Docs",
            local_path=str(tmp_path),
            remote_path="gdrive:Docs",
            run_on_startup=True,
            realtime=True,
            transfers=8,
            checkers=16,
            ignore_patterns=["*.tmp"],
            include_patterns=["Docs/**"],
        )
    )
    export_file = tmp_path / "jobs.json"

    assert export_jobs(source_db, export_file) == 1

    target_db = Database(tmp_path / "target.db")
    target_db.initialize()

    assert import_jobs(target_db, export_file) == 1

    job = target_db.get_job("Docs")
    assert job is not None
    assert job.run_on_startup
    assert job.realtime
    assert job.transfers == 8
    assert job.checkers == 16
    assert job.ignore_patterns == ["*.tmp"]
    assert job.include_patterns == ["Docs/**"]
