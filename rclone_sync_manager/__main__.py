from __future__ import annotations

import sys

from .cli import main


def run() -> int:
    args = sys.argv[1:] or ["gui"]
    return main(args)


if __name__ == "__main__":
    raise SystemExit(run())
