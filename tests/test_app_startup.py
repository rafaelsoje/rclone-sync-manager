from pathlib import Path

from rclone_sync_manager.database import Database
from rclone_sync_manager.models import Job
from rclone_sync_manager.startup import enqueue_startup_jobs


class FakeQueue:
    def __init__(self) -> None:
        self.jobs = []

    def enqueue(self, job: Job) -> None:
        self.jobs.append(job)


def test_enqueue_startup_jobs_only_enqueues_enabled_marked_jobs(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    marked = db.create_job(
        Job(
            name="Marked",
            local_path=str(tmp_path),
            remote_path="gdrive:Marked",
            run_on_startup=True,
        )
    )
    db.create_job(Job(name="Manual", local_path=str(tmp_path), remote_path="gdrive:Manual"))
    disabled = db.create_job(
        Job(
            name="Disabled",
            local_path=str(tmp_path),
            remote_path="gdrive:Disabled",
            run_on_startup=True,
        )
    )
    db.set_job_enabled(disabled.name, False)
    queue = FakeQueue()

    count = enqueue_startup_jobs(db, queue)

    assert count == 1
    assert [job.name for job in queue.jobs] == [marked.name]
