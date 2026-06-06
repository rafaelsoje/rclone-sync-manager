from __future__ import annotations

import fnmatch
import re
import shlex
import subprocess
from pathlib import Path

from .platform_utils import is_windows


SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def shell_join(command: list[str]) -> str:
    if is_windows():
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def safe_filename(value: str) -> str:
    cleaned = SAFE_FILENAME_RE.sub("_", value.strip())
    return cleaned.strip("._") or "job"


def path_matches_patterns(path: str | Path, patterns: list[str], base_path: str | Path | None = None) -> bool:
    candidate = Path(path)
    if base_path:
        try:
            candidate_text = candidate.relative_to(base_path).as_posix()
        except ValueError:
            candidate_text = candidate.as_posix()
    else:
        candidate_text = candidate.as_posix()

    name = candidate.name
    for pattern in patterns:
        normalized = pattern.strip()
        if not normalized:
            continue
        if fnmatch.fnmatch(candidate_text, normalized) or fnmatch.fnmatch(name, normalized):
            return True
    return False
