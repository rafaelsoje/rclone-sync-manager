from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SyncMode(StrEnum):
    COPY = "copy"
    SYNC = "sync"
    BISYNC = "bisync"


class SyncDirection(StrEnum):
    LOCAL_TO_REMOTE = "local_to_remote"
    REMOTE_TO_LOCAL = "remote_to_local"


class JobStatus(StrEnum):
    IDLE = "idle"
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    STOPPED = "stopped"
    PAUSED = "paused"
    DISABLED = "disabled"
    WAITING_DEBOUNCE = "waiting_debounce"
    SCHEDULED = "scheduled"


@dataclass(slots=True)
class Job:
    name: str
    local_path: str
    remote_path: str
    mode: str = SyncMode.COPY.value
    direction: str = SyncDirection.LOCAL_TO_REMOTE.value
    id: int | None = None
    enabled: bool = True
    run_on_startup: bool = False
    realtime: bool = False
    schedule_time: str | None = None
    debounce_seconds: int = 30
    transfers: int = 4
    checkers: int = 8
    bandwidth_limit: str | None = None
    dry_run: bool = False
    priority_low: bool = True
    notify: bool = True
    ignore_patterns: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class JobRun:
    job_id: int
    started_at: str
    finished_at: str | None = None
    status: str = JobStatus.RUNNING.value
    exit_code: int | None = None
    duration_seconds: int | None = None
    command: str | None = None
    log_file: str | None = None
    error_message: str | None = None
    id: int | None = None


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()
