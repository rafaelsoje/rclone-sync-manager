from pathlib import Path
import json
import subprocess
import sys

from rclone_sync_manager.lock_manager import LockManager
from rclone_sync_manager.models import Job


def test_lock_lifecycle(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=tmp_path)
    job = Job(id=1, name="Documentos", local_path="/tmp", remote_path="gdrive:Documentos")

    assert not manager.is_locked(job)
    manager.create_lock(job)
    assert manager.is_locked(job)
    manager.remove_lock(job)
    assert not manager.is_locked(job)


def test_lock_with_stale_pid_is_removed(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=tmp_path)
    job = Job(id=1, name="Documentos", local_path="/tmp", remote_path="gdrive:Documentos")
    path = manager.lock_path(job)
    path.write_text(json.dumps({"pid": 999999999, "job": job.name}), encoding="utf-8")

    assert not manager.is_locked(job)
    assert not path.exists()


def test_create_lock_uses_given_pid(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=tmp_path)
    job = Job(id=1, name="Documentos", local_path="/tmp", remote_path="gdrive:Documentos")

    path = manager.create_lock(job, pid=123)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["pid"] == 123


def test_stop_job_terminates_locked_process(tmp_path: Path) -> None:
    manager = LockManager(lock_dir=tmp_path)
    job = Job(id=1, name="Documentos", local_path="/tmp", remote_path="gdrive:Documentos")
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

    try:
        manager.create_lock(job, pid=process.pid)

        assert manager.stop_job(job)
        process.wait(timeout=5)
        assert process.returncode is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
