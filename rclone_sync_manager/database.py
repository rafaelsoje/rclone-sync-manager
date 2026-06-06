from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .config import ensure_app_dirs, get_app_paths
from .models import Job, JobRun, JobStatus, now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    enabled INTEGER DEFAULT 1,
    run_on_startup INTEGER DEFAULT 0,
    local_path TEXT NOT NULL,
    remote_path TEXT NOT NULL,
    mode TEXT NOT NULL,
    direction TEXT DEFAULT 'local_to_remote',
    realtime INTEGER DEFAULT 0,
    schedule_time TEXT NULL,
    debounce_seconds INTEGER DEFAULT 30,
    transfers INTEGER DEFAULT 4,
    checkers INTEGER DEFAULT 8,
    bandwidth_limit TEXT NULL,
    dry_run INTEGER DEFAULT 0,
    priority_low INTEGER DEFAULT 1,
    notify INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS ignore_patterns (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL,
    pattern TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS include_patterns (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL,
    pattern TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    exit_code INTEGER,
    duration_seconds INTEGER,
    command TEXT,
    log_file TEXT,
    error_message TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS job_state (
    job_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    message TEXT,
    updated_at TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
"""


class Database:
    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path:
            self.db_path = Path(db_path)
        else:
            paths = ensure_app_dirs()
            self.db_path = paths.db_file
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    def create_job(self, job: Job) -> Job:
        self._validate_job(job)
        created_at = now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    name, enabled, run_on_startup, local_path, remote_path, mode, direction, realtime,
                    schedule_time, debounce_seconds, transfers, checkers,
                    bandwidth_limit, dry_run, priority_low, notify, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.name,
                    int(job.enabled),
                    int(job.run_on_startup),
                    job.local_path,
                    job.remote_path,
                    job.mode,
                    job.direction,
                    int(job.realtime),
                    job.schedule_time,
                    job.debounce_seconds,
                    job.transfers,
                    job.checkers,
                    job.bandwidth_limit,
                    int(job.dry_run),
                    int(job.priority_low),
                    int(job.notify),
                    created_at,
                    created_at,
                ),
            )
            job_id = int(cursor.lastrowid)
            self._replace_ignore_patterns(conn, job_id, job.ignore_patterns)
            self._replace_include_patterns(conn, job_id, job.include_patterns)
            self._set_job_state(conn, job_id, "idle" if job.enabled else "paused", None)
        return self.get_job(job.name)  # type: ignore[return-value]

    def update_job(self, job: Job) -> Job:
        if job.id is None:
            raise ValueError("job.id is required for update")
        self._validate_job(job)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET name = ?, enabled = ?, run_on_startup = ?, local_path = ?, remote_path = ?, mode = ?,
                    direction = ?, realtime = ?, schedule_time = ?, debounce_seconds = ?, transfers = ?,
                    checkers = ?, bandwidth_limit = ?, dry_run = ?, priority_low = ?,
                    notify = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    job.name,
                    int(job.enabled),
                    int(job.run_on_startup),
                    job.local_path,
                    job.remote_path,
                    job.mode,
                    job.direction,
                    int(job.realtime),
                    job.schedule_time,
                    job.debounce_seconds,
                    job.transfers,
                    job.checkers,
                    job.bandwidth_limit,
                    int(job.dry_run),
                    int(job.priority_low),
                    int(job.notify),
                    now_iso(),
                    job.id,
                ),
            )
            self._replace_ignore_patterns(conn, job.id, job.ignore_patterns)
            self._replace_include_patterns(conn, job.id, job.include_patterns)
            if not job.enabled:
                self._set_job_state(conn, job.id, "paused", None)
        return self.get_job(job.name)  # type: ignore[return-value]

    def delete_job(self, name: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE name = ?", (name,))

    def get_job(self, name: str) -> Job | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE name = ?", (name,)).fetchone()
            if row is None:
                return None
            return self._row_to_job(conn, row)

    def list_jobs(self) -> list[Job]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY name").fetchall()
            return [self._row_to_job(conn, row) for row in rows]

    def get_job_by_id(self, job_id: int) -> Job | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_job(conn, row)

    def set_job_enabled(self, name: str, enabled: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET enabled = ?, updated_at = ? WHERE name = ?",
                (int(enabled), now_iso(), name),
            )
            row = conn.execute("SELECT id FROM jobs WHERE name = ?", (name,)).fetchone()
            if row:
                self._set_job_state(conn, row["id"], "idle" if enabled else "paused", None)

    def create_job_run(self, run: JobRun) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO job_runs (
                    job_id, started_at, finished_at, status, exit_code,
                    duration_seconds, command, log_file, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.job_id,
                    run.started_at,
                    run.finished_at,
                    run.status,
                    run.exit_code,
                    run.duration_seconds,
                    run.command,
                    run.log_file,
                    run.error_message,
                ),
            )
            return int(cursor.lastrowid)

    def finish_job_run(
        self,
        run_id: int,
        *,
        status: str,
        exit_code: int | None,
        finished_at: str,
        duration_seconds: int,
        error_message: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE job_runs
                SET status = ?, exit_code = ?, finished_at = ?,
                    duration_seconds = ?, error_message = ?
                WHERE id = ?
                """,
                (status, exit_code, finished_at, duration_seconds, error_message, run_id),
            )

    def reconcile_interrupted_jobs(self, active_job_ids: Iterable[int] = ()) -> int:
        active_ids = set(active_job_ids)
        transient_statuses = (
            JobStatus.PENDING.value,
            JobStatus.RUNNING.value,
            JobStatus.WAITING_DEBOUNCE.value,
            JobStatus.SCHEDULED.value,
        )
        placeholders = ", ".join("?" for _ in transient_statuses)
        finished_at = now_iso()
        message = "execução anterior não estava mais ativa ao iniciar o app"
        updated = 0
        with self.connect() as conn:
            state_rows = conn.execute(
                f"""
                SELECT jobs.id, jobs.enabled
                FROM jobs
                JOIN job_state ON job_state.job_id = jobs.id
                WHERE job_state.status IN ({placeholders})
                """,
                transient_statuses,
            ).fetchall()
            for row in state_rows:
                job_id = int(row["id"])
                if job_id in active_ids:
                    continue
                status = JobStatus.PAUSED.value if not row["enabled"] else JobStatus.STOPPED.value
                self._set_job_state(conn, job_id, status, message)
                updated += 1

            run_rows = conn.execute(
                f"""
                SELECT id, job_id, started_at
                FROM job_runs
                WHERE finished_at IS NULL AND status IN ({placeholders})
                """,
                transient_statuses,
            ).fetchall()
            for row in run_rows:
                if int(row["job_id"]) in active_ids:
                    continue
                conn.execute(
                    """
                    UPDATE job_runs
                    SET status = ?, finished_at = ?, duration_seconds = ?, error_message = ?
                    WHERE id = ?
                    """,
                    (
                        JobStatus.STOPPED.value,
                        finished_at,
                        _duration_seconds(row["started_at"], finished_at),
                        message,
                        row["id"],
                    ),
                )
                updated += 1
        return updated

    def set_job_status(self, job_id: int, status: str, message: str | None = None) -> None:
        with self.connect() as conn:
            self._set_job_state(conn, job_id, status, message)

    def get_job_status(self, job_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM job_state WHERE job_id = ?", (job_id,)).fetchone()

    def get_job_status_text(self, job_id: int, default: str = "idle") -> str:
        row = self.get_job_status(job_id)
        return row["status"] if row else default

    def _set_job_state(
        self,
        conn: sqlite3.Connection,
        job_id: int,
        status: str,
        message: str | None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO job_state(job_id, status, message, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status = excluded.status,
                message = excluded.message,
                updated_at = excluded.updated_at
            """,
            (job_id, status, message, now_iso()),
        )

    def get_last_job_run(self, job_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM job_runs
                WHERE job_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()

    def list_job_runs(self, job_id: int, limit: int = 50) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM job_runs
                WHERE job_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def _row_to_job(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Job:
        ignore_patterns = [
            pattern_row["pattern"]
            for pattern_row in conn.execute(
                "SELECT pattern FROM ignore_patterns WHERE job_id = ? ORDER BY id",
                (row["id"],),
            )
        ]
        include_patterns = [
            pattern_row["pattern"]
            for pattern_row in conn.execute(
                "SELECT pattern FROM include_patterns WHERE job_id = ? ORDER BY id",
                (row["id"],),
            )
        ]
        return Job(
            id=row["id"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            run_on_startup=bool(row["run_on_startup"]),
            local_path=row["local_path"],
            remote_path=row["remote_path"],
            mode=row["mode"],
            direction=row["direction"] or "local_to_remote",
            realtime=bool(row["realtime"]),
            schedule_time=row["schedule_time"],
            debounce_seconds=row["debounce_seconds"],
            transfers=row["transfers"],
            checkers=row["checkers"],
            bandwidth_limit=row["bandwidth_limit"],
            dry_run=bool(row["dry_run"]),
            priority_low=bool(row["priority_low"]),
            notify=bool(row["notify"]),
            ignore_patterns=ignore_patterns,
            include_patterns=include_patterns,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _replace_ignore_patterns(
        self, conn: sqlite3.Connection, job_id: int, patterns: Iterable[str]
    ) -> None:
        conn.execute("DELETE FROM ignore_patterns WHERE job_id = ?", (job_id,))
        conn.executemany(
            "INSERT INTO ignore_patterns(job_id, pattern) VALUES(?, ?)",
            [(job_id, pattern) for pattern in patterns if pattern.strip()],
        )

    def _replace_include_patterns(
        self, conn: sqlite3.Connection, job_id: int, patterns: Iterable[str]
    ) -> None:
        conn.execute("DELETE FROM include_patterns WHERE job_id = ?", (job_id,))
        conn.executemany(
            "INSERT INTO include_patterns(job_id, pattern) VALUES(?, ?)",
            [(job_id, pattern) for pattern in patterns if pattern.strip()],
        )

    def _validate_job(self, job: Job) -> None:
        if not job.name.strip():
            raise ValueError("job name is required")
        local_path = Path(job.local_path)
        if job.direction == "remote_to_local":
            local_path.mkdir(parents=True, exist_ok=True)
        if not local_path.is_dir():
            raise ValueError(f"local path is not a directory: {job.local_path}")
        if not job.remote_path.strip():
            raise ValueError("remote path is required")
        if job.mode not in {"copy", "sync", "bisync"}:
            raise ValueError("mode must be copy, sync, or bisync")
        if job.direction not in {"local_to_remote", "remote_to_local"}:
            raise ValueError("direction must be local_to_remote or remote_to_local")
        if job.mode == "bisync" and job.direction != "local_to_remote":
            raise ValueError("bisync does not support direction; use local_to_remote")
        if job.debounce_seconds <= 5:
            raise ValueError("debounce_seconds must be greater than 5")
        if job.transfers < 1:
            raise ValueError("transfers must be at least 1")
        if job.checkers < 1:
            raise ValueError("checkers must be at least 1")

    def _migrate(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "direction" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN direction TEXT DEFAULT 'local_to_remote'")
        if "run_on_startup" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN run_on_startup INTEGER DEFAULT 0")


def init_default_database() -> Database:
    ensure_app_dirs(get_app_paths())
    db = Database()
    db.initialize()
    return db


def _duration_seconds(started_at: str | None, finished_at: str) -> int:
    if not started_at:
        return 0
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return 0
    return max(0, int((finished - started).total_seconds()))
