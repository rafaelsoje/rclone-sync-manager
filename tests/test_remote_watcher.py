from pathlib import Path

from rclone_sync_manager.database import Database
from rclone_sync_manager.models import Job
from rclone_sync_manager.queue_manager import QueueManager
from rclone_sync_manager import remote_watcher
from rclone_sync_manager.remote_watcher import RemotePoller, RemotePollerManager


class FakePoller:
    def __init__(self, job, queue_manager, rclone_path="rclone") -> None:
        self.job = job
        self.stopped = False

    def start(self) -> None:
        return None

    def stop(self) -> None:
        self.stopped = True


def test_remote_poller_manager_tracks_remote_to_local_jobs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    monkeypatch.setattr(remote_watcher, "RemotePoller", FakePoller)
    manager = RemotePollerManager(QueueManager(db=db))
    job = db.create_job(
        Job(
            name="Restore",
            local_path=str(tmp_path),
            remote_path="dropbox:Restore",
            direction="remote_to_local",
            realtime=True,
        )
    )

    manager.sync_jobs([job])

    assert manager.watched_jobs() == {"Restore"}
    manager.stop_all()


def test_remote_poller_enqueues_initial_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    job = db.create_job(
        Job(
            name="Restore",
            local_path=str(tmp_path),
            remote_path="dropbox:Restore",
            direction="remote_to_local",
            realtime=True,
        )
    )
    queue_manager = QueueManager(db=db)
    poller = RemotePoller(job, queue_manager)

    assert poller.handle_snapshot("file.txt;123;2026-05-14\n")
    assert db.get_job_status_text(job.id) == "pending"
    assert not poller.handle_snapshot("file.txt;123;2026-05-14\n")
    assert poller.handle_snapshot("file.txt;124;2026-05-14\n")
