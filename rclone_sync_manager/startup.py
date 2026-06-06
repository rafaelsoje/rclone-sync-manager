from __future__ import annotations

from .database import Database
from .queue_manager import QueueManager


def enqueue_startup_jobs(db: Database, queue_manager: QueueManager) -> int:
    count = 0
    for job in db.list_jobs():
        if job.enabled and job.run_on_startup:
            queue_manager.enqueue(job)
            count += 1
    return count
