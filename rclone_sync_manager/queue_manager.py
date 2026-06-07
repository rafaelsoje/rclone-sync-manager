from __future__ import annotations

import queue
import threading

from .database import Database
from .models import Job, JobStatus
from .runner import RcloneRunner, STOPPED_EXIT_CODES


class QueueManager:
    def __init__(self, db: Database | None = None, max_parallel: int = 1) -> None:
        self.db = db or Database()
        self.runner = RcloneRunner(db=self.db)
        self.max_parallel = max(1, max_parallel)
        self._queue: queue.Queue[Job] = queue.Queue()
        self._running: set[str] = set()
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self.errors: dict[str, Exception] = {}

    def start(self) -> None:
        if self._workers:
            return
        for index in range(self.max_parallel):
            worker = threading.Thread(target=self.worker_loop, name=f"rsm-worker-{index}", daemon=True)
            worker.start()
            self._workers.append(worker)

    def stop(self) -> None:
        self._stop.set()
        for worker in self._workers:
            worker.join(timeout=2)

    def enqueue(self, job: Job) -> None:
        if job.id is not None:
            self.db.set_job_status(job.id, JobStatus.PENDING.value)
        with self._lock:
            if job.name in self._running:
                self._pending.add(job.name)
                return
        self._queue.put(job)

    def mark_pending(self, job: Job) -> None:
        if job.id is not None:
            self.db.set_job_status(job.id, JobStatus.PENDING.value)
        with self._lock:
            self._pending.add(job.name)

    def is_running(self, job: Job | str) -> bool:
        name = job.name if isinstance(job, Job) else job
        with self._lock:
            return name in self._running

    def worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._lock:
                if job.name in self._running:
                    self._pending.add(job.name)
                    if job.id is not None:
                        self.db.set_job_status(job.id, JobStatus.PENDING.value)
                    self._queue.task_done()
                    continue
                self._running.add(job.name)
            try:
                if job.id is not None:
                    fresh_job = self.db.get_job_by_id(job.id)
                    if fresh_job is None:
                        continue
                    job = fresh_job
                    self.db.set_job_status(job.id, JobStatus.RUNNING.value)
                result = self.runner.run(job)
                if job.id is not None:
                    self.db.set_job_status(
                        job.id,
                        _status_from_exit_code(result.exit_code),
                        result.error_message,
                    )
            except Exception as exc:
                self.errors[job.name] = exc
                if job.id is not None:
                    self.db.set_job_status(job.id, JobStatus.ERROR.value, str(exc))
            finally:
                rerun = False
                with self._lock:
                    self._running.discard(job.name)
                    rerun = job.name in self._pending
                    self._pending.discard(job.name)
                self._queue.task_done()
                if rerun:
                    if job.id is not None:
                        self.db.set_job_status(job.id, JobStatus.WAITING_DEBOUNCE.value)
                    timer = threading.Timer(job.debounce_seconds, lambda: self._queue.put(job))
                    timer.daemon = True
                    timer.start()


def _status_from_exit_code(exit_code: int) -> str:
    if exit_code == 0:
        return JobStatus.SUCCESS.value
    if exit_code in STOPPED_EXIT_CODES:
        return JobStatus.STOPPED.value
    return JobStatus.ERROR.value
