from __future__ import annotations

import json
import os
import signal
from pathlib import Path

from .config import ensure_app_dirs
from .models import Job, now_iso
from .utils import safe_filename

try:
    import psutil
except ImportError:  # pragma: no cover - exercised only in minimal environments
    psutil = None


class LockManager:
    def __init__(self, lock_dir: str | Path | None = None) -> None:
        if lock_dir:
            self.lock_dir = Path(lock_dir)
        else:
            paths = ensure_app_dirs()
            self.lock_dir = paths.lock_dir
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    def lock_path(self, job: Job | str) -> Path:
        name = job.name if isinstance(job, Job) else job
        return self.lock_dir / f"{safe_filename(name)}.lock"

    def is_locked(self, job: Job | str) -> bool:
        return self.locked_pid(job) is not None

    def read_lock(self, job: Job | str) -> dict | None:
        path = self.lock_path(job)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            pid = int(payload["pid"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            return None
        if pid_exists(pid):
            return payload
        path.unlink(missing_ok=True)
        return None

    def locked_pid(self, job: Job | str) -> int | None:
        payload = self.read_lock(job)
        if payload is None:
            return None
        try:
            return int(payload["pid"])
        except (ValueError, KeyError):
            self.remove_lock(job)
            return None

    def create_lock(self, job: Job, pid: int | None = None) -> Path:
        if self.is_locked(job):
            raise RuntimeError(f"job already locked: {job.name}")
        path = self.lock_path(job)
        payload = {"pid": pid or os.getpid(), "job": job.name, "started_at": now_iso()}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def remove_lock(self, job: Job | str) -> None:
        self.lock_path(job).unlink(missing_ok=True)

    def stop_job(self, job: Job | str) -> bool:
        pid = self.locked_pid(job)
        if pid is None:
            return False
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self.remove_lock(job)
            return False
        except PermissionError:
            return False
        return True

    def cleanup_stale_locks(self) -> int:
        removed = 0
        for path in self.lock_dir.glob("*.lock"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                pid = int(payload["pid"])
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                path.unlink(missing_ok=True)
                removed += 1
                continue
            if not pid_exists(pid):
                try:
                    path.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    continue
        return removed


def pid_exists(pid: int) -> bool:
    if psutil is not None:
        return bool(psutil.pid_exists(pid))
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
