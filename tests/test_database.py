from pathlib import Path

from rclone_sync_manager.database import Database
from rclone_sync_manager.models import Job, JobRun, JobStatus


def test_create_and_list_job(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()

    db.create_job(Job(name="Docs", local_path=str(tmp_path), remote_path="gdrive:Docs"))
    jobs = db.list_jobs()

    assert len(jobs) == 1
    assert jobs[0].name == "Docs"
    assert jobs[0].direction == "local_to_remote"
    assert not jobs[0].run_on_startup
    assert jobs[0].ignore_patterns == []
    assert db.get_job_status_text(jobs[0].id) == "idle"


def test_create_job_with_run_on_startup(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()

    db.create_job(
        Job(
            name="Docs",
            local_path=str(tmp_path),
            remote_path="gdrive:Docs",
            run_on_startup=True,
        )
    )

    job = db.get_job("Docs")
    assert job.run_on_startup


def test_create_job_with_ignore_patterns(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()

    db.create_job(
        Job(
            name="Docs",
            local_path=str(tmp_path),
            remote_path="gdrive:Docs",
            ignore_patterns=["*.tmp"],
        )
    )

    job = db.get_job("Docs")
    assert job.ignore_patterns == ["*.tmp"]


def test_create_job_with_include_patterns(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()

    db.create_job(
        Job(
            name="Photos",
            local_path=str(tmp_path),
            remote_path="photos:",
            include_patterns=["media/all/**"],
        )
    )

    job = db.get_job("Photos")
    assert job.include_patterns == ["media/all/**"]


def test_last_job_run(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    job = db.create_job(Job(name="Docs", local_path=str(tmp_path), remote_path="gdrive:Docs"))

    run_id = db.create_job_run(JobRun(job_id=job.id, started_at="2026-05-14T10:00:00"))
    db.finish_job_run(
        run_id,
        status="success",
        exit_code=0,
        finished_at="2026-05-14T10:00:03",
        duration_seconds=3,
    )

    last_run = db.get_last_job_run(job.id)
    assert last_run is not None
    assert last_run["status"] == "success"


def test_job_status_lifecycle(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    job = db.create_job(Job(name="Docs", local_path=str(tmp_path), remote_path="gdrive:Docs"))

    db.set_job_status(job.id, "pending")
    assert db.get_job_status_text(job.id) == "pending"

    db.set_job_enabled(job.name, False)
    assert db.get_job_status_text(job.id) == "paused"


def test_reconcile_interrupted_jobs_marks_stale_running_state(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    job = db.create_job(Job(name="Docs", local_path=str(tmp_path), remote_path="gdrive:Docs"))
    db.create_job_run(JobRun(job_id=job.id, started_at="2026-05-14T10:00:00"))
    db.set_job_status(job.id, JobStatus.RUNNING.value)

    updated = db.reconcile_interrupted_jobs()
    last_run = db.get_last_job_run(job.id)

    assert updated == 2
    assert db.get_job_status_text(job.id) == JobStatus.STOPPED.value
    assert last_run["status"] == JobStatus.STOPPED.value
    assert last_run["finished_at"] is not None
    assert last_run["error_message"] == "execução anterior não estava mais ativa ao iniciar o app"


def test_reconcile_interrupted_jobs_keeps_active_job_running(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    job = db.create_job(Job(name="Docs", local_path=str(tmp_path), remote_path="gdrive:Docs"))
    db.create_job_run(JobRun(job_id=job.id, started_at="2026-05-14T10:00:00"))
    db.set_job_status(job.id, JobStatus.RUNNING.value)

    updated = db.reconcile_interrupted_jobs(active_job_ids=[job.id])
    last_run = db.get_last_job_run(job.id)

    assert updated == 0
    assert db.get_job_status_text(job.id) == JobStatus.RUNNING.value
    assert last_run["status"] == JobStatus.RUNNING.value
    assert last_run["finished_at"] is None


def test_remote_to_local_realtime_is_valid(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()

    job = db.create_job(
        Job(
            name="Restore",
            local_path=str(tmp_path),
            remote_path="dropbox:Restore",
            direction="remote_to_local",
            realtime=True,
        )
    )

    assert job.realtime


def test_remote_to_local_creates_missing_local_directory(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    local_path = tmp_path / "missing" / "restore"

    db.create_job(
        Job(
            name="Restore",
            local_path=str(local_path),
            remote_path="dropbox:Restore",
            direction="remote_to_local",
        )
    )

    assert local_path.is_dir()


def test_local_to_remote_requires_existing_local_directory(tmp_path: Path) -> None:
    db = Database(tmp_path / "rsm.db")
    db.initialize()
    local_path = tmp_path / "missing"

    try:
        db.create_job(Job(name="Upload", local_path=str(local_path), remote_path="dropbox:Upload"))
    except ValueError as exc:
        assert "local path is not a directory" in str(exc)
    else:
        raise AssertionError("expected missing local source to fail")
    assert not local_path.exists()
