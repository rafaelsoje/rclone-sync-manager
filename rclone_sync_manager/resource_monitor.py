from __future__ import annotations

from dataclasses import dataclass

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


@dataclass(slots=True)
class ResourceSnapshot:
    cpu_percent: float | None
    memory_percent: float | None


def snapshot() -> ResourceSnapshot:
    if psutil is None:
        return ResourceSnapshot(cpu_percent=None, memory_percent=None)
    return ResourceSnapshot(
        cpu_percent=psutil.cpu_percent(interval=None),
        memory_percent=psutil.virtual_memory().percent,
    )
