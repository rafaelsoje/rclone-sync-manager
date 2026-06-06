from pathlib import Path
from types import SimpleNamespace

from rclone_sync_manager.database import Database
from rclone_sync_manager.models import Job, JobStatus
from rclone_sync_manager.queue_manager import QueueManager


def test_enqueue_marks_job_pending(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    job = db.create_job(Job(name="Docs", local_path=str(tmp_path), remote_path="gdrive:Docs"))

    manager = QueueManager(db=db)
    manager.enqueue(job)

    assert db.get_job_status_text(job.id) == "pending"


def test_queue_preserves_stopped_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    job = db.create_job(Job(name="Docs", local_path=str(tmp_path), remote_path="gdrive:Docs"))
    manager = QueueManager(db=db)

    class FakeRunner:
        def run(self, job: Job):
            return SimpleNamespace(exit_code=-15, error_message="parado")

    manager.runner = FakeRunner()
    manager.start()
    manager.enqueue(job)
    manager._queue.join()
    manager.stop()

    assert db.get_job_status_text(job.id) == JobStatus.STOPPED.value
