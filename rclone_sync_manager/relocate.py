from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .database import Database
    from .models import Job


def relocate_job_path(
    db: Database,
    job: Job,
    new_local_path: str | Path,
    *,
    move_files: bool = True,
    resync_bisync: bool = True,
) -> tuple[bool, str]:
    """
    Move os arquivos locais com segurança e reconfigura o Job para o novo caminho.
    Se for bisync, redefine o estado e reexecuta --resync para que o rclone crie a nova
    listagem de referência sem baixar tudo novamente da nuvem.
    """
    from .lock_manager import LockManager
    from .runner import RcloneRunner

    old_path = Path(job.local_path).resolve()
    new_path = Path(new_local_path).expanduser().resolve()

    if old_path == new_path:
        return True, "O caminho de origem e destino são idênticos."

    if new_path.is_relative_to(old_path):
        raise ValueError("O novo destino não pode ser uma subpasta da pasta antiga.")
    if old_path.is_relative_to(new_path):
        raise ValueError("A pasta antiga não pode ser uma subpasta do novo destino.")

    locks = LockManager()
    locks.cleanup_stale_locks()
    if locks.is_locked(job):
        raise RuntimeError(f"A tarefa '{job.name}' está em execução no momento. Pare-a antes de alterar o local.")

    new_path.mkdir(parents=True, exist_ok=True)

    if move_files and old_path.exists() and old_path.is_dir():
        for item in old_path.iterdir():
            dest_item = new_path / item.name
            if dest_item.exists():
                if item.is_dir():
                    shutil.copytree(str(item), str(dest_item), dirs_exist_ok=True)
                    shutil.rmtree(str(item))
                else:
                    item.replace(dest_item)
            else:
                shutil.move(str(item), str(dest_item))
        try:
            old_path.rmdir()
        except OSError:
            pass

    job.local_path = str(new_path)
    db.update_job(job)
    db.set_setting(f"bisync_initialized:{job.id}", "false")

    if job.mode == "bisync" and resync_bisync and job.enabled:
        runner = RcloneRunner(db=db)
        run_res = runner.run(job, resync=True)
        if run_res.exit_code != 0:
            return False, f"Arquivos movidos para {new_path}, mas o bisync inicial retornou código {run_res.exit_code}. Verifique os logs."

    return True, f"Tarefa e arquivos migrados com sucesso para {new_path}."
