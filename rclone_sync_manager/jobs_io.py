from __future__ import annotations

import json
from pathlib import Path

from .database import Database
from .models import Job


JOB_EXPORT_VERSION = 1

JOB_FIELDS = [
    "name",
    "enabled",
    "run_on_startup",
    "local_path",
    "remote_path",
    "mode",
    "direction",
    "realtime",
    "schedule_time",
    "debounce_seconds",
    "transfers",
    "checkers",
    "bandwidth_limit",
    "dry_run",
    "priority_low",
    "notify",
    "ignore_patterns",
    "include_patterns",
]


def export_jobs(db: Database, path: str | Path) -> int:
    payload = {"version": JOB_EXPORT_VERSION, "jobs": [_job_to_dict(job) for job in db.list_jobs()]}
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(payload["jobs"])


def import_jobs(db: Database, path: str | Path, *, overwrite: bool = True) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    imported = 0
    for raw_job in payload.get("jobs", []):
        job = _job_from_dict(raw_job)
        existing = db.get_job(job.name)
        if existing is not None:
            if not overwrite:
                continue
            job.id = existing.id
            db.update_job(job)
        else:
            db.create_job(job)
        imported += 1
    return imported


def _job_to_dict(job: Job) -> dict:
    return {field: getattr(job, field) for field in JOB_FIELDS}


def _job_from_dict(data: dict) -> Job:
    values = {field: data.get(field) for field in JOB_FIELDS}
    values["ignore_patterns"] = values.get("ignore_patterns") or []
    values["include_patterns"] = values.get("include_patterns") or []
    return Job(**values)
