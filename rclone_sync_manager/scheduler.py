from __future__ import annotations

import threading
import time
from datetime import datetime

from .database import Database
from .queue_manager import QueueManager


class DailyScheduler:
    def __init__(self, db: Database, queue_manager: QueueManager) -> None:
        self.db = db
        self.queue_manager = queue_manager
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run: set[tuple[str, str]] = set()

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self.loop, name="rsm-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def loop(self) -> None:
        while not self._stop.is_set():
            now = datetime.now()
            today = now.date().isoformat()
            current_time = now.strftime("%H:%M")
            for job in self.db.list_jobs():
                key = (job.name, today)
                if job.enabled and job.schedule_time == current_time and key not in self._last_run:
                    self.queue_manager.enqueue(job)
                    self._last_run.add(key)
            time.sleep(30)
