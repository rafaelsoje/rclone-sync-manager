from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .platform_utils import config_home, data_home


APP_NAME = "rclone-sync-manager"

DEFAULT_IGNORE_PATTERNS = [
    "*.tmp",
    "*.temp",
    "*.part",
    "*.crdownload",
    "~*",
    "~$*",
    "*.swp",
    "*.swo",
    "*.swx",
    ".~lock.*#",
    ".nfs*",
    ".DS_Store",
    "Desktop.ini",
    "desktop.ini",
    "Thumbs.db",
    "thumbs.db",
    "ehthumbs.db",
    "$RECYCLE.BIN/**",
    "System Volume Information/**",
    ".Trash/**",
    ".Trash-*/**",
    "node_modules/**",
    "__pycache__/**",
    "vendor/**",
    "storage/logs/**",
]


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    config_file: Path
    data_dir: Path
    db_file: Path
    log_dir: Path
    job_log_dir: Path
    state_dir: Path
    lock_dir: Path


def get_app_paths() -> AppPaths:
    config_dir = config_home() / APP_NAME
    data_dir = data_home() / APP_NAME
    log_dir = data_dir / "logs"
    return AppPaths(
        config_dir=config_dir,
        config_file=config_dir / "config.yaml",
        data_dir=data_dir,
        db_file=data_dir / "rsm.db",
        log_dir=log_dir,
        job_log_dir=log_dir / "jobs",
        state_dir=data_dir / "state",
        lock_dir=data_dir / "locks",
    )


def ensure_app_dirs(paths: AppPaths | None = None) -> AppPaths:
    paths = paths or get_app_paths()
    for directory in (
        paths.config_dir,
        paths.data_dir,
        paths.log_dir,
        paths.job_log_dir,
        paths.state_dir,
        paths.lock_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def load_config(paths: AppPaths | None = None) -> dict:
    paths = paths or ensure_app_dirs()
    if not paths.config_file.exists():
        return {}
    with paths.config_file.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
