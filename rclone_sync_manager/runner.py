from __future__ import annotations

import subprocess
import signal
import shlex
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

STOPPED_EXIT_CODES = {-signal.SIGTERM, signal.SIGTERM, 128 + signal.SIGTERM}


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
        for flag in job.extra_flags:
            if flag and flag.strip():
                parts = shlex.split(flag) if " " in flag else [flag]
                command.extend(part.strip() for part in parts if part.strip())
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
        local_path = Path(job.local_path)
        if not local_path.exists():
            try:
                local_path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise RuntimeError(f"failed to create local directory {local_path}: {exc}") from exc
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
        raw_error = ""
        exit_code = 1
        if job.mode == "bisync":
            from .lock_manager import cleanup_stale_bisync_locks
            cleanup_stale_bisync_locks()
        try:
            self.db.set_job_status(job.id, JobStatus.RUNNING.value)
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.locks.create_lock(job, pid=process.pid)
            stdout, stderr = process.communicate()
            completed = subprocess.CompletedProcess(command, process.returncode, stdout=stdout, stderr=stderr)
            exit_code = completed.returncode
            if completed.returncode != 0:
                raw_error = (completed.stderr or completed.stdout).strip()
                if not raw_error and log_file.exists():
                    raw_error = _extract_last_error_from_log(log_file)
                error_message = _friendly_error_message(raw_error)
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
            if job.mode == "bisync":
                if resync and exit_code == 0:
                    self.db.set_setting(f"bisync_initialized:{job.id}", "true")
                elif exit_code != 0 and (
                    "must run --resync" in (raw_error or "").lower()
                    or "cannot find prior path" in (raw_error or "").lower()
                ):
                    self.db.set_setting(f"bisync_initialized:{job.id}", "false")
            if exit_code != 0 and status != JobStatus.STOPPED.value:
                detail = error_message or f"rclone retornou código {exit_code}"
                self._notify(job, "Erro de sincronização", f"{job.name}: {detail}", is_error=True)
            elif self.db.get_setting("notify_success", "false") == "true":
                self._notify(job, "Sincronização concluída", f"{job.name} finalizado com sucesso.")
            self.locks.remove_lock(job)

        return RunResult(
            exit_code=exit_code,
            command=command,
            log_file=log_file,
            duration_seconds=duration,
            error_message=error_message,
        )

    def _notify(self, job: Job, title: str, message: str, is_error: bool = False) -> None:
        notifications_enabled = self.db.get_setting("notifications", "true") == "true"
        if not notifications_enabled:
            return
        if not job.notify:
            return
        notify(title, message)


def _status_from_exit_code(exit_code: int) -> str:
    if exit_code == 0:
        return JobStatus.SUCCESS.value
    if exit_code in STOPPED_EXIT_CODES:
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
    if "cannotdownloadabusivefile" in lowered or "drive-acknowledge-abuse" in lowered:
        return (
            "O Google Drive bloqueou o download de arquivo identificado como suspeito ou malware "
            "(ex: scripts, executáveis .exe antigos).\n"
            "A flag '--drive-acknowledge-abuse' foi adicionada às flags extras do job para permitir a sincronização.\n\n"
            f"{message}"
        )
    if "must run --resync" in lowered or "cannot find prior path" in lowered:
        return (
            "O rclone bisync perdeu os índices de sincronização anteriores (devido a interrupção ou conflito) "
            "e precisa restabelecer a base com --resync.\n"
            "Reinicialize a tarefa clicando em 'Inicializar bisync' na interface ou executando: rsm init-bisync --job <Nome>.\n\n"
            f"{message}"
        )
    return message


def _extract_last_error_from_log(log_file: Path, max_lines: int = 60) -> str:
    if not log_file.exists():
        return ""
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        errors = [line for line in lines[-max_lines:] if "ERROR :" in line or "critical error" in line.lower()]
        if errors:
            return "\n".join(errors[-3:])
        return "\n".join(lines[-5:])
    except Exception:
        return ""
