from __future__ import annotations

import configparser
import json
import shlex
from pathlib import Path
from typing import Any

from .models import Job, SyncDirection, SyncMode


def _is_remote_path(path: str) -> bool:
    return ":" in path and not (path.startswith("/") or path.startswith("~"))


def job_to_conf_dict(job: Job) -> dict[str, str]:
    """Serializa um Job para um dicionário de valores de string para arquivo .conf (INI)."""
    # Determina source e destination com base no mode e direction
    if job.mode == SyncMode.BISYNC.value:
        source = job.remote_path if _is_remote_path(job.remote_path) else job.local_path
        dest = job.local_path if source == job.remote_path else job.remote_path
    elif job.direction == SyncDirection.REMOTE_TO_LOCAL.value:
        source = job.remote_path
        dest = job.local_path
    else:
        source = job.local_path
        dest = job.remote_path

    data: dict[str, str] = {
        "name": job.name,
        "enabled": "true" if job.enabled else "false",
        "action": job.mode,
        "source": source,
        "destination": dest,
        "realtime": "true" if job.realtime else "false",
        "run_on_startup": "true" if job.run_on_startup else "false",
        "debounce": str(job.debounce_seconds),
        "transfers": str(job.transfers),
        "checkers": str(job.checkers),
        "dry_run": "true" if job.dry_run else "false",
        "priority_low": "true" if job.priority_low else "false",
        "notify": "true" if job.notify else "false",
    }
    if job.bandwidth_limit:
        data["bandwidth_limit"] = job.bandwidth_limit
    if job.schedule_time:
        data["schedule_time"] = job.schedule_time
    if job.ignore_patterns:
        data["exclusions"] = ", ".join(job.ignore_patterns)
    if job.include_patterns:
        data["inclusions"] = ", ".join(job.include_patterns)
    if job.extra_flags:
        data["flags"] = " ".join(job.extra_flags)
    return data


def job_from_conf_section(section_name: str, options: dict[str, str]) -> Job:
    """Cria um objeto Job a partir de uma seção de arquivo .conf (INI)."""
    name = options.get("name", "").strip() or section_name.strip()
    action = options.get("action") or options.get("mode") or SyncMode.COPY.value
    if action not in {SyncMode.COPY.value, SyncMode.SYNC.value, SyncMode.BISYNC.value}:
        action = SyncMode.COPY.value

    # Resolução de source e destination
    local_path = options.get("local_path", "").strip()
    remote_path = options.get("remote_path", "").strip()
    direction = options.get("direction", "").strip()

    if not local_path or not remote_path:
        source = options.get("source", "").strip()
        destination = options.get("destination", "").strip()
        if _is_remote_path(source):
            remote_path = source
            local_path = destination
            if not direction:
                direction = SyncDirection.REMOTE_TO_LOCAL.value
        else:
            local_path = source
            remote_path = destination
            if not direction:
                direction = SyncDirection.LOCAL_TO_REMOTE.value

    if not direction:
        direction = SyncDirection.LOCAL_TO_REMOTE.value
    if action == SyncMode.BISYNC.value:
        direction = SyncDirection.LOCAL_TO_REMOTE.value

    # Parse de listas
    exclusions_raw = options.get("exclusions") or options.get("ignore_patterns") or ""
    ignore_patterns = [p.strip() for p in exclusions_raw.split(",") if p.strip()] if exclusions_raw else []

    inclusions_raw = options.get("inclusions") or options.get("include_patterns") or ""
    include_patterns = [p.strip() for p in inclusions_raw.split(",") if p.strip()] if inclusions_raw else []

    flags_raw = options.get("flags") or options.get("extra_flags") or ""
    extra_flags = [f.strip() for f in shlex.split(flags_raw) if f.strip()] if flags_raw else []

    def _to_bool(val: str | None, default: bool) -> bool:
        if val is None:
            return default
        return val.strip().lower() in {"1", "true", "yes", "on"}

    def _to_int(val: str | None, default: int) -> int:
        if not val:
            return default
        try:
            return int(val.strip())
        except ValueError:
            return default

    debounce = _to_int(options.get("debounce") or options.get("debounce_seconds"), 30)
    if debounce <= 5:
        debounce = 6

    return Job(
        name=name,
        local_path=local_path,
        remote_path=remote_path,
        mode=action,
        direction=direction,
        enabled=_to_bool(options.get("enabled"), True),
        run_on_startup=_to_bool(options.get("run_on_startup"), False),
        realtime=_to_bool(options.get("realtime"), False),
        schedule_time=options.get("schedule_time") or options.get("poll_interval"),
        debounce_seconds=debounce,
        transfers=_to_int(options.get("transfers"), 4),
        checkers=_to_int(options.get("checkers"), 8),
        bandwidth_limit=options.get("bandwidth_limit") or options.get("bwlimit"),
        dry_run=_to_bool(options.get("dry_run"), False),
        priority_low=_to_bool(options.get("priority_low"), True),
        notify=_to_bool(options.get("notify"), True),
        ignore_patterns=ignore_patterns,
        include_patterns=include_patterns,
        extra_flags=extra_flags,
    )


def parse_conf_text(text: str) -> list[Job]:
    """Lê uma string no formato INI/.conf e retorna uma lista de Jobs."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    jobs: list[Job] = []
    for section in parser.sections():
        options = dict(parser.items(section))
        jobs.append(job_from_conf_section(section, options))
    return jobs


def dump_conf_text(jobs: list[Job]) -> str:
    """Exporta uma lista de Jobs para uma string no formato .conf (INI)."""
    parser = configparser.ConfigParser(interpolation=None)
    for job in jobs:
        section = job.name.replace(" ", "-").lower() if job.name else "job"
        # Garante seção única
        base_section = section
        counter = 1
        while parser.has_section(section):
            section = f"{base_section}-{counter}"
            counter += 1
        parser.add_section(section)
        for k, v in job_to_conf_dict(job).items():
            parser.set(section, k, v)
    import io
    out = io.StringIO()
    parser.write(out)
    return out.getvalue()


def job_to_json_dict(job: Job) -> dict[str, Any]:
    """Converte um Job para o dicionário JSON padrão."""
    data = {
        "id": job.name.replace(" ", "-").lower() if job.name else "job",
        "name": job.name,
        "enabled": job.enabled,
        "action": job.mode,
        "direction": job.direction,
        "local_path": job.local_path,
        "remote_path": job.remote_path,
        "realtime": job.realtime,
        "run_on_startup": job.run_on_startup,
        "debounce_seconds": job.debounce_seconds,
        "transfers": job.transfers,
        "checkers": job.checkers,
        "bandwidth_limit": job.bandwidth_limit,
        "dry_run": job.dry_run,
        "priority_low": job.priority_low,
        "notify": job.notify,
        "exclusions": job.ignore_patterns,
        "inclusions": job.include_patterns,
        "flags": job.extra_flags,
    }
    if job.schedule_time:
        data["schedule_time"] = job.schedule_time
    return data


def job_from_json_dict(data: dict[str, Any]) -> Job:
    """Cria um Job a partir de um dicionário JSON (suporta schemas 'tasks' e 'jobs')."""
    # Se os campos forem do formato antigo (jobs_io) ou novo padrão
    name = data.get("name") or data.get("id") or "unnamed"
    action = data.get("action") or data.get("mode") or SyncMode.COPY.value
    direction = data.get("direction") or SyncDirection.LOCAL_TO_REMOTE.value

    local_path = data.get("local_path") or ""
    remote_path = data.get("remote_path") or ""
    if not local_path or not remote_path:
        source = data.get("source") or ""
        destination = data.get("destination") or ""
        if _is_remote_path(source):
            remote_path = source
            local_path = destination
            if "direction" not in data:
                direction = SyncDirection.REMOTE_TO_LOCAL.value
        else:
            local_path = source
            remote_path = destination

    exclusions = data.get("exclusions") or data.get("ignore_patterns") or []
    if isinstance(exclusions, str):
        exclusions = [x.strip() for x in exclusions.split(",") if x.strip()]

    inclusions = data.get("inclusions") or data.get("include_patterns") or []
    if isinstance(inclusions, str):
        inclusions = [x.strip() for x in inclusions.split(",") if x.strip()]

    flags = data.get("flags") or data.get("extra_flags") or []
    if isinstance(flags, str):
        flags = [x.strip() for x in shlex.split(flags) if x.strip()]

    debounce = data.get("debounce_seconds") or data.get("debounce") or 30
    if isinstance(debounce, str):
        try:
            debounce = int(debounce)
        except ValueError:
            debounce = 30
    if debounce <= 5:
        debounce = 6

    return Job(
        name=name,
        local_path=local_path,
        remote_path=remote_path,
        mode=action,
        direction=direction,
        enabled=bool(data.get("enabled", True)),
        run_on_startup=bool(data.get("run_on_startup", False)),
        realtime=bool(data.get("realtime", False)),
        schedule_time=data.get("schedule_time") or data.get("poll_interval"),
        debounce_seconds=debounce,
        transfers=int(data.get("transfers", 4)),
        checkers=int(data.get("checkers", 8)),
        bandwidth_limit=data.get("bandwidth_limit") or data.get("bwlimit"),
        dry_run=bool(data.get("dry_run", False)),
        priority_low=bool(data.get("priority_low", True)),
        notify=bool(data.get("notify", True)),
        ignore_patterns=list(exclusions),
        include_patterns=list(inclusions),
        extra_flags=list(flags),
    )


def parse_json_text(text: str) -> list[Job]:
    """Lê JSON e retorna lista de Jobs (suporta {"tasks": [...]}, {"jobs": [...]}, ou lista direta)."""
    payload = json.loads(text)
    raw_list: list[dict[str, Any]]
    if isinstance(payload, list):
        raw_list = payload
    elif isinstance(payload, dict):
        raw_list = payload.get("tasks") or payload.get("jobs") or [payload]
    else:
        raise ValueError("JSON inválido: esperado objeto ou lista de tarefas")
    return [job_from_json_dict(item) for item in raw_list if isinstance(item, dict)]


def dump_json_text(jobs: list[Job]) -> str:
    """Exporta lista de Jobs para JSON formatado."""
    payload = {
        "version": 1,
        "tasks": [job_to_json_dict(job) for job in jobs],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def load_rules_file(path: str | Path) -> list[Job]:
    """Carrega regras de um arquivo .conf ou .json automaticamente."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Arquivo de regras não encontrado: {path}")
    content = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        return parse_json_text(content)
    # Padrão ou .conf
    return parse_conf_text(content)


def load_rules_directory(dir_path: str | Path) -> list[Job]:
    """Escaneia um diretório por arquivos .conf e .json e retorna todos os Jobs carregados."""
    p = Path(dir_path)
    if not p.is_dir():
        return []
    jobs: list[Job] = []
    # Busca arquivos ordenados
    for file_path in sorted(list(p.glob("*.conf")) + list(p.glob("*.json"))):
        try:
            jobs.extend(load_rules_file(file_path))
        except Exception:
            continue
    return jobs
