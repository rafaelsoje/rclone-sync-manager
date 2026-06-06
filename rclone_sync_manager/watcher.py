from __future__ import annotations

import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .models import Job
from .queue_manager import QueueManager
from .utils import path_matches_patterns


class DebouncedJobHandler(FileSystemEventHandler):
    def __init__(self, job: Job, queue_manager: QueueManager) -> None:
        self.job = job
        self.queue_manager = queue_manager
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if self.job.id is not None:
            self.queue_manager.db.set_job_status(self.job.id, "waiting_debounce")
        paths = [event.src_path]
        dest_path = getattr(event, "dest_path", None)
        if dest_path:
            paths.append(dest_path)
        if any(
            path_matches_patterns(path, self.job.ignore_patterns, self.job.local_path)
            for path in paths
        ):
            return
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.job.debounce_seconds, self._enqueue)
            self._timer.daemon = True
            self._timer.start()

    def _enqueue(self) -> None:
        self.queue_manager.enqueue(self.job)


class WatcherManager:
    def __init__(self, queue_manager: QueueManager) -> None:
        self.queue_manager = queue_manager
        self._observers: dict[str, Observer] = {}

    def start_job(self, job: Job) -> None:
        if (
            not job.enabled
            or not job.realtime
            or job.direction != "local_to_remote"
            or job.name in self._observers
        ):
            return
        path = Path(job.local_path)
        if not path.exists():
            raise FileNotFoundError(job.local_path)
        observer = Observer()
        observer.schedule(DebouncedJobHandler(job, self.queue_manager), str(path), recursive=True)
        observer.start()
        self._observers[job.name] = observer

    def sync_jobs(self, jobs: list[Job]) -> None:
        wanted = {
            job.name: job
            for job in jobs
            if job.enabled and job.realtime and job.direction == "local_to_remote"
        }
        for job_name in list(self._observers):
            if job_name not in wanted:
                self.stop_job(job_name)
        for job in wanted.values():
            if job.name not in self._observers:
                self.start_job(job)

    def watched_jobs(self) -> set[str]:
        return set(self._observers)

    def stop_job(self, job_name: str) -> None:
        observer = self._observers.pop(job_name, None)
        if observer is None:
            return
        observer.stop()
        observer.join(timeout=5)

    def stop_all(self) -> None:
        for job_name in list(self._observers):
            self.stop_job(job_name)
