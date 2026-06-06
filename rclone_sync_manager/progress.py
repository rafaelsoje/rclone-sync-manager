from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ProgressSnapshot:
    percent: int | None = None
    transferred: str | None = None
    speed: str | None = None
    eta: str | None = None
    checks: str | None = None
    errors: str | None = None
    elapsed: str | None = None
    transferring: list[str] | None = None


def progress_from_log(log_file: str | Path) -> int | None:
    return progress_snapshot_from_log(log_file).percent


def progress_snapshot_from_log(log_file: str | Path) -> ProgressSnapshot:
    path = Path(log_file)
    if not path.exists():
        return ProgressSnapshot()
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(size - 120_000, 0))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ProgressSnapshot()

    transferred_match = _last_match(
        r"Transferred:\s+(?P<done>[^,\n]+(?:\s*/\s*[^,\n]+)?),\s+"
        r"(?:(?P<percent>\d{1,3})%,\s+)?"
        r"(?P<speed>[^,\n]+/s)(?:,\s+ETA\s+(?P<eta>[^\n,]+))?",
        text,
    )
    percent = None
    transferred = None
    speed = None
    eta = None
    if transferred_match:
        transferred = transferred_match.group("done").strip()
        speed = transferred_match.group("speed").strip()
        eta = transferred_match.group("eta")
        if eta:
            eta = eta.strip()
        raw_percent = transferred_match.group("percent")
        if raw_percent is not None:
            percent = max(0, min(100, int(raw_percent)))

    checks_match = _last_match(r"Checks:\s+([^\n]+)", text)
    errors_match = _last_match(r"Errors:\s+([^\n]+)", text)
    elapsed_match = _last_match(r"Elapsed time:\s+([^\n]+)", text)
    transferring = _latest_transferring_entries(text)

    return ProgressSnapshot(
        percent=percent,
        transferred=transferred,
        speed=speed,
        eta=eta,
        checks=checks_match.group(1).strip() if checks_match else None,
        errors=errors_match.group(1).strip() if errors_match else None,
        elapsed=elapsed_match.group(1).strip() if elapsed_match else None,
        transferring=transferring,
    )


def _last_match(pattern: str, text: str) -> re.Match[str] | None:
    matches = list(re.finditer(pattern, text))
    return matches[-1] if matches else None


def _latest_transferring_entries(text: str) -> list[str]:
    lines = text.splitlines()
    entries: list[str] = []
    in_block = False
    for line in reversed(lines):
        stripped = line.strip()
        if stripped == "Transferring:":
            return list(reversed(entries))
        if stripped.startswith("* "):
            in_block = True
            entries.append(stripped[2:].strip())
            continue
        if in_block and stripped:
            break
    return []
