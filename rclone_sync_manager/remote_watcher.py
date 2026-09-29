from __future__ import annotations

import subprocess
import threading
import time

from .models import Job
from .queue_manager import QueueManager


class RemotePoller:
    def __init__(self, job: Job, queue_manager: QueueManager, rclone_path: str = "rclone") -> None:
        self.job = job
        self.queue_manager = queue_manager
        self.rclone_path = rclone_path
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_snapshot: str | None = None

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self.loop, name=f"rsm-remote-{self.job.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def loop(self) -> None:
        interval = max(10, self.job.debounce_seconds)
        while not self._stop.is_set():
            snapshot = remote_snapshot(self.job.remote_path, self.rclone_path)
            self.handle_snapshot(snapshot)
            self._stop.wait(interval)

    def handle_snapshot(self, snapshot: str | None) -> bool:
        if snapshot is None:
            return False
        if self._last_snapshot is None:
            self._last_snapshot = snapshot
            self._enqueue("remote initial sync")
            return True
        if snapshot != self._last_snapshot:
            self._last_snapshot = snapshot
            self._enqueue("remote change detected")
            return True
        return False

    def _enqueue(self, message: str) -> None:
        if self.job.id is not None:
            self.queue_manager.db.set_job_status(self.job.id, "pending", message)
        self.queue_manager.enqueue(self.job)


class RemotePollerManager:
    def __init__(self, queue_manager: QueueManager, rclone_path: str = "rclone") -> None:
        self.queue_manager = queue_manager
        self.rclone_path = rclone_path
        self._pollers: dict[str, RemotePoller] = {}

    def sync_jobs(self, jobs: list[Job]) -> None:
        wanted = {
            job.name: job
            for job in jobs
            if job.enabled and job.realtime and job.direction == "remote_to_local"
        }
        for job_name in list(self._pollers):
            if job_name not in wanted:
                self.stop_job(job_name)
        for job in wanted.values():
            if job.name not in self._pollers:
                self.start_job(job)

    def start_job(self, job: Job) -> None:
        poller = RemotePoller(job, self.queue_manager, self.rclone_path)
        poller.start()
        self._pollers[job.name] = poller

    def stop_job(self, job_name: str) -> None:
        poller = self._pollers.pop(job_name, None)
        if poller:
            poller.stop()

    def stop_all(self) -> None:
        for job_name in list(self._pollers):
            self.stop_job(job_name)

    def watched_jobs(self) -> set[str]:
        return set(self._pollers)


def remote_snapshot(remote_path: str, rclone_path: str = "rclone") -> str | None:
    try:
        completed = subprocess.run(
            [rclone_path, "lsf", remote_path, "--recursive", "--format", "pst"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout
