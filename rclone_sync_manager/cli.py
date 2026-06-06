from __future__ import annotations

import argparse
from pathlib import Path

from .config import ensure_app_dirs
from .database import Database, init_default_database
from .doctor import has_failures, run_checks
from .models import Job
from .systemd import is_service_active, service_status, set_autostart
from .utils import safe_filename


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rsm", description="Rclone Sync Manager")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create app directories and SQLite schema")
    sub.add_parser("list", help="list configured jobs")
    sub.add_parser("status", help="show job status summary")
    sub.add_parser("doctor", help="check local requirements")
    gui = sub.add_parser("gui", help="open graphical interface")
    gui.add_argument(
        "--start-hidden",
        action="store_true",
        help="start runtime and tray icon without showing the main window",
    )
    sub.add_parser("start", help="start background service loop")
    sub.add_parser("enable-service", help="enable and start the systemd user service")
    sub.add_parser("disable-service", help="disable and stop the systemd user service")
    sub.add_parser("service-status", help="show the systemd user service status")
    sub.add_parser("cleanup-locks", help="remove stale job locks")
    export_cmd = sub.add_parser("export-jobs", help="export jobs to JSON")
    export_cmd.add_argument("path")
    import_cmd = sub.add_parser("import-jobs", help="import jobs from JSON")
    import_cmd.add_argument("path")

    add = sub.add_parser("add-job", help="create a sync job")
    add.add_argument("--name", required=True)
    add.add_argument("--local", required=True)
    add.add_argument("--remote", required=True)
    add.add_argument("--mode", choices=["copy", "sync", "bisync"], default="copy")
    add.add_argument(
        "--direction",
        choices=["local-to-remote", "remote-to-local"],
        default="local-to-remote",
        help="copy/sync direction; bisync is always bidirectional",
    )
    add.add_argument("--realtime", action="store_true")
    add.add_argument("--run-on-startup", action="store_true")
    add.add_argument("--schedule-time")
    add.add_argument("--debounce", type=int, default=30)
    add.add_argument("--transfers", type=int, default=4)
    add.add_argument("--checkers", type=int, default=8)
    add.add_argument("--bwlimit")
    add.add_argument("--dry-run", action="store_true")
    add.add_argument("--no-low-priority", action="store_true")
    add.add_argument("--no-notify", action="store_true")
    add.add_argument("--ignore", action="append", default=[])

    run = sub.add_parser("run", help="run sync now")
    target = run.add_mutually_exclusive_group(required=True)
    target.add_argument("--job")
    target.add_argument("--all", action="store_true")

    init_bisync = sub.add_parser("init-bisync", help="run first bisync with --resync")
    init_bisync.add_argument("--job", required=True)

    for name in ("pause", "resume", "logs"):
        command = sub.add_parser(name)
        command.add_argument("--job", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = ensure_app_dirs()
    db = init_default_database()

    if args.command == "init":
        print(f"Initialized Rclone Sync Manager at {paths.data_dir}")
        return 0
    if args.command == "add-job":
        job = Job(
            name=args.name,
            local_path=str(Path(args.local).expanduser()),
            remote_path=args.remote,
            mode=args.mode,
            direction=args.direction.replace("-", "_"),
            run_on_startup=args.run_on_startup,
            realtime=args.realtime,
            schedule_time=args.schedule_time,
            debounce_seconds=args.debounce,
            transfers=args.transfers,
            checkers=args.checkers,
            bandwidth_limit=args.bwlimit,
            dry_run=args.dry_run,
            priority_low=not args.no_low_priority,
            notify=not args.no_notify,
            ignore_patterns=args.ignore,
        )
        created = db.create_job(job)
        print(f"Created job {created.name}")
        return 0
    if args.command == "list":
        return list_jobs(db)
    if args.command == "status":
        return status(db)
    if args.command == "run":
        from .runner import RcloneRunner

        runner = RcloneRunner(db=db)
        jobs = db.list_jobs() if args.all else [require_job(db, args.job)]
        exit_code = 0
        for job in jobs:
            result = runner.run(job)
            print(f"{job.name}: exit={result.exit_code} log={result.log_file}")
            exit_code = max(exit_code, result.exit_code)
        return exit_code
    if args.command == "init-bisync":
        from .runner import RcloneRunner

        job = require_job(db, args.job)
        if job.mode != "bisync":
            raise SystemExit(f"job is not bisync: {job.name}")
        result = RcloneRunner(db=db).run(job, resync=True)
        print(f"{job.name}: exit={result.exit_code} log={result.log_file}")
        return result.exit_code
    if args.command == "pause":
        db.set_job_enabled(args.job, False)
        print(f"Paused {args.job}")
        return 0
    if args.command == "resume":
        db.set_job_enabled(args.job, True)
        print(f"Resumed {args.job}")
        return 0
    if args.command == "logs":
        job = require_job(db, args.job)
        log_file = paths.job_log_dir / f"{safe_filename(job.name)}.log"
        if not log_file.exists():
            print(f"No log found for {job.name}: {log_file}")
            return 1
        print(log_file.read_text(encoding="utf-8", errors="replace")[-8000:])
        return 0
    if args.command == "doctor":
        return doctor(db)
    if args.command == "enable-service":
        result = set_autostart(True)
        db.set_setting("autostart", "true" if result.ok else "false")
        print(result.output or "Service enabled.")
        return 0 if result.ok else 1
    if args.command == "disable-service":
        result = set_autostart(False)
        db.set_setting("autostart", "false")
        print(result.output or "Service disabled.")
        return 0 if result.ok else 1
    if args.command == "service-status":
        result = service_status()
        print(result.output or ("active" if result.ok else "inactive"))
        return 0 if result.ok else 1
    if args.command == "cleanup-locks":
        from .lock_manager import LockManager

        removed = LockManager().cleanup_stale_locks()
        print(f"Removed {removed} stale lock(s).")
        return 0
    if args.command == "export-jobs":
        from .jobs_io import export_jobs

        count = export_jobs(db, args.path)
        print(f"Exported {count} job(s) to {args.path}")
        return 0
    if args.command == "import-jobs":
        from .jobs_io import import_jobs

        count = import_jobs(db, args.path, overwrite=True)
        print(f"Imported {count} job(s) from {args.path}")
        return 0
    if args.command == "gui":
        from .app import run_gui

        return run_gui(start_hidden=args.start_hidden)
    if args.command == "start":
        from .app import run_service

        return run_service()
    return 1


def require_job(db: Database, name: str) -> Job:
    job = db.get_job(name)
    if job is None:
        raise SystemExit(f"job not found: {name}")
    return job


def list_jobs(db: Database) -> int:
    jobs = db.list_jobs()
    if not jobs:
        print("No jobs configured.")
        return 0
    for job in jobs:
        state = "enabled" if job.enabled else "paused"
        print(f"{job.name}\t{job.mode}\t{job.direction}\t{state}\t{job.local_path}\t{job.remote_path}")
    return 0


def status(db: Database) -> int:
    jobs = db.list_jobs()
    print(f"Jobs: {len(jobs)}")
    print(f"Service: {'active' if is_service_active() else 'inactive'}")
    for job in jobs:
        state = "enabled" if job.enabled else "disabled"
        realtime = "realtime" if job.realtime else "manual"
        schedule = job.schedule_time or "-"
        last_run = db.get_last_job_run(job.id) if job.id is not None else None
        runtime_status = db.get_job_status_text(job.id) if job.id is not None else "idle"
        last = "-"
        if last_run:
            last = f"{last_run['status']} exit={last_run['exit_code']} at={last_run['finished_at'] or last_run['started_at']}"
        print(
            f"{job.name}: {state}, runtime={runtime_status}, direction={job.direction}, "
            f"{realtime}, schedule={schedule}, last={last}"
        )
    return 0


def doctor(db: Database) -> int:
    checks = run_checks(db)
    for check in checks:
        print(f"{'OK' if check.ok else 'FAIL'}\t{check.name}\t{check.detail}")
    return 1 if has_failures(checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
