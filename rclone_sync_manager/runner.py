from __future__ import annotations

import subprocess
import signal
import time
from dataclasses import dataclass
from pathlib import Path

from .config import ensure_app_dirs
from .database import Database
from .lock_manager import LockManager
from .models import Job, JobRun, JobStatus, now_iso
from .notifier import notify
from .platform_utils import is_windows
from .utils import safe_filename, shell_join


@dataclass(slots=True)
class RunResult:
    exit_code: int
    command: list[str]
    log_file: Path
    duration_seconds: int
    error_message: str | None = None


class RcloneRunner:
    def __init__(
        self,
        db: Database | None = None,
        locks: LockManager | None = None,
        rclone_path: str = "rclone",
    ) -> None:
        self.paths = ensure_app_dirs()
        self.db = db or Database()
        self.db.initialize()
        self.locks = locks or LockManager()
        self.rclone_path = rclone_path

    def build_command(self, job: Job, *, resync: bool = False) -> tuple[list[str], Path]:
        if job.mode not in {"copy", "sync", "bisync"}:
            raise ValueError(f"unsupported rclone mode: {job.mode}")

        log_file = self.paths.job_log_dir / f"{safe_filename(job.name)}.log"
        source, destination = self._source_destination(job)
        command: list[str] = []
        if job.priority_low and not is_windows():
            command.extend(["ionice", "-c3", "nice", "-n", "19"])
        command.extend([self.rclone_path, job.mode, source, destination])
        command.extend(["--transfers", str(job.transfers)])
        command.extend(["--checkers", str(job.checkers)])
        if job.bandwidth_limit:
            command.extend(["--bwlimit", job.bandwidth_limit])
        for pattern in job.include_patterns:
            if pattern.strip():
                command.extend(["--include", pattern.strip()])
        for pattern in job.ignore_patterns:
            if pattern.strip():
                command.extend(["--exclude", pattern.strip()])
        if any(pattern.strip() for pattern in job.include_patterns):
            command.extend(["--exclude", "**"])
        if job.dry_run:
            command.append("--dry-run")
        if job.mode == "bisync" and resync:
            command.append("--resync")
        command.extend(
            [
                "--stats",
                "5s",
                "--stats-log-level",
                "INFO",
                "--log-file",
                str(log_file),
                "--log-level",
                "INFO",
            ]
        )
        return command, log_file

    def _source_destination(self, job: Job) -> tuple[str, str]:
        if job.mode == "bisync":
            return job.local_path, job.remote_path
        if job.direction == "remote_to_local":
            return job.remote_path, job.local_path
        return job.local_path, job.remote_path

    def run(self, job: Job, *, resync: bool = False) -> RunResult:
        if job.id is None:
            raise ValueError("job must be persisted before running")
        if not job.enabled:
            raise RuntimeError(f"job is disabled: {job.name}")
        if job.mode == "bisync" and not resync:
            initialized = self.db.get_setting(f"bisync_initialized:{job.id}", "false")
            if initialized != "true":
                raise RuntimeError(f"bisync must be initialized first: rsm init-bisync --job {job.name}")
        self.locks.cleanup_stale_locks()
        if self.locks.is_locked(job):
            raise RuntimeError(f"job is already running: {job.name}")

        command, log_file = self.build_command(job, resync=resync)
        started = time.monotonic()
        run_id = self.db.create_job_run(
            JobRun(
                job_id=job.id,
                started_at=now_iso(),
                command=shell_join(command),
                log_file=str(log_file),
            )
        )
        error_message = None
        exit_code = 1
        try:
            self.db.set_job_status(job.id, JobStatus.RUNNING.value)
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.locks.create_lock(job, pid=process.pid)
            self._notify(job, "Sincronização iniciada", f"{job.name} está rodando.")
            stdout, stderr = process.communicate()
            completed = subprocess.CompletedProcess(command, process.returncode, stdout=stdout, stderr=stderr)
            exit_code = completed.returncode
            if completed.returncode != 0:
                error_message = _friendly_error_message((completed.stderr or completed.stdout).strip())
        except FileNotFoundError as exc:
            error_message = str(exc)
            exit_code = 127
        finally:
            duration = int(time.monotonic() - started)
            status = _status_from_exit_code(exit_code)
            if status == JobStatus.STOPPED.value and error_message is None:
                error_message = "processo interrompido pelo usuário"
            self.db.finish_job_run(
                run_id,
                status=status,
                exit_code=exit_code,
                finished_at=now_iso(),
                duration_seconds=duration,
                error_message=error_message,
            )
            self.db.set_job_status(job.id, status, error_message)
            if job.mode == "bisync" and resync and exit_code == 0:
                self.db.set_setting(f"bisync_initialized:{job.id}", "true")
            if exit_code == 0:
                self._notify(job, "Sincronização concluída", f"{job.name} finalizado com sucesso.")
            elif status == JobStatus.STOPPED.value:
                self._notify(job, "Sincronização parada", f"{job.name} foi interrompido.")
            else:
                detail = error_message or f"rclone retornou código {exit_code}"
                self._notify(job, "Erro de sincronização", f"{job.name}: {detail}")
            self.locks.remove_lock(job)

        return RunResult(
            exit_code=exit_code,
            command=command,
            log_file=log_file,
            duration_seconds=duration,
            error_message=error_message,
        )

    def _notify(self, job: Job, title: str, message: str) -> None:
        notifications_enabled = self.db.get_setting("notifications", "true") == "true"
        if job.notify and notifications_enabled:
            notify(title, message)


def _status_from_exit_code(exit_code: int) -> str:
    if exit_code == 0:
        return JobStatus.SUCCESS.value
    if exit_code in {-signal.SIGTERM, 128 + signal.SIGTERM}:
        return JobStatus.STOPPED.value
    return JobStatus.ERROR.value


def _friendly_error_message(message: str | None) -> str | None:
    if not message:
        return None
    lowered = message.lower()
    if "corrupted on transfer" in lowered or "corrupt" in lowered:
        return (
            "Arquivo corrompido durante a transferencia. O rclone normalmente remove o "
            "arquivo parcial e tenta novamente; se persistir, confira conexao, disco local "
            "e tente reduzir transfers/checkers.\n\n"
            f"{message}"
        )
    if "failed to copy" in lowered or "failed to transfer" in lowered:
        return (
            "Falha ao copiar um ou mais arquivos. Veja o log do job para identificar quais "
            "arquivos falharam e se o rclone esta tentando novamente.\n\n"
            f"{message}"
        )
    if "access is denied" in lowered or "permission denied" in lowered:
        return f"Permissao negada. Confira acesso a pasta local/remoto e arquivos em uso.\n\n{message}"
    if "directory not found" in lowered or "not a directory" in lowered:
        return f"Diretório não encontrado. Confira origem/destino e filtros.\n\n{message}"
    if "didn't find section" in lowered or "couldn't find root" in lowered or "config file" in lowered:
        return f"Remote rclone não encontrado ou configuração inválida.\n\n{message}"
    if "token" in lowered or "unauthorized" in lowered or "forbidden" in lowered or "auth" in lowered:
        return f"Falha de autenticação/permissão no remote. Talvez seja preciso reconectar com rclone config.\n\n{message}"
    if "rate limit" in lowered or "too many requests" in lowered or "quota" in lowered:
        return f"Limite do provedor atingido. Tente reduzir transfers/checkers ou aguardar.\n\n{message}"
    return message
