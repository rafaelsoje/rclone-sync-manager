from __future__ import annotations

from pathlib import Path
from rclone_sync_manager.models import Job, SyncDirection, SyncMode
from rclone_sync_manager.rules_manager import (
    dump_conf_text,
    dump_json_text,
    load_rules_directory,
    load_rules_file,
    parse_conf_text,
    parse_json_text,
)


def test_conf_parsing_and_dump() -> None:
    conf_content = """
[meus-documentos]
name = Meus Documentos Pessoais
enabled = true
action = bisync
source = drive:Documentos
destination = /tmp/test-docs
exclusions = .git/**, node_modules/**, *.tmp
flags = --fast-list --drive-skip-gdocs --transfers 4
debounce = 15
transfers = 4
dry_run = false

[backup-fotos]
name = Backup Fotos
enabled = false
action = copy
source = /tmp/test-fotos
destination = drive:FotosBackup
flags = --bwlimit 10M
"""
    jobs = parse_conf_text(conf_content)
    assert len(jobs) == 2

    job1 = jobs[0]
    assert job1.name == "Meus Documentos Pessoais"
    assert job1.mode == SyncMode.BISYNC.value
    assert job1.remote_path == "drive:Documentos"
    assert job1.local_path == "/tmp/test-docs"
    assert job1.enabled is True
    assert job1.debounce_seconds == 15
    assert job1.ignore_patterns == [".git/**", "node_modules/**", "*.tmp"]
    assert job1.extra_flags == ["--fast-list", "--drive-skip-gdocs", "--transfers", "4"]

    job2 = jobs[1]
    assert job2.name == "Backup Fotos"
    assert job2.mode == SyncMode.COPY.value
    assert job2.enabled is False
    assert job2.local_path == "/tmp/test-fotos"
    assert job2.remote_path == "drive:FotosBackup"
    assert job2.direction == SyncDirection.LOCAL_TO_REMOTE.value
    assert job2.extra_flags == ["--bwlimit", "10M"]

    # Dump roundtrip test
    dumped = dump_conf_text(jobs)
    reloaded = parse_conf_text(dumped)
    assert len(reloaded) == 2
    assert reloaded[0].name == job1.name
    assert reloaded[0].mode == job1.mode
    assert reloaded[0].ignore_patterns == job1.ignore_patterns


def test_json_parsing_and_dump() -> None:
    json_content = """
{
  "tasks": [
    {
      "id": "sync-docs",
      "name": "Sync Docs",
      "enabled": true,
      "action": "sync",
      "direction": "remote_to_local",
      "local_path": "/tmp/docs",
      "remote_path": "drive:Docs",
      "exclusions": ["*.log", ".cache/**"],
      "flags": ["--drive-chunk-size=32M", "--fast-list"],
      "debounce_seconds": 20
    }
  ]
}
"""
    jobs = parse_json_text(json_content)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.name == "Sync Docs"
    assert job.mode == "sync"
    assert job.direction == "remote_to_local"
    assert job.local_path == "/tmp/docs"
    assert job.remote_path == "drive:Docs"
    assert job.ignore_patterns == ["*.log", ".cache/**"]
    assert job.extra_flags == ["--drive-chunk-size=32M", "--fast-list"]
    assert job.debounce_seconds == 20

    dumped = dump_json_text(jobs)
    reloaded = parse_json_text(dumped)
    assert len(reloaded) == 1
    assert reloaded[0].name == "Sync Docs"
    assert reloaded[0].extra_flags == ["--drive-chunk-size=32M", "--fast-list"]


def test_load_rules_directory(tmp_path: Path) -> None:
    conf_file = tmp_path / "tarefas.conf"
    conf_file.write_text("""
[job-conf]
name = Job From Conf
source = /tmp/local
destination = drive:remote
action = copy
""", encoding="utf-8")

    json_file = tmp_path / "tarefas.json"
    json_file.write_text("""
{
  "tasks": [
    {
      "name": "Job From Json",
      "source": "drive:remote2",
      "destination": "/tmp/local2",
      "action": "sync"
    }
  ]
}
""", encoding="utf-8")

    loaded = load_rules_directory(tmp_path)
    assert len(loaded) == 2
    names = {j.name for j in loaded}
    assert "Job From Conf" in names
    assert "Job From Json" in names
