from __future__ import annotations

import sys

from rclone_sync_manager import __main__


def test_module_entrypoint_defaults_to_gui(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_main(args: list[str]) -> int:
        calls.append(args)
        return 0

    monkeypatch.setattr(sys, "argv", ["rclone_sync_manager"])
    monkeypatch.setattr(__main__, "main", fake_main)

    assert __main__.run() == 0
    assert calls == [["gui"]]


def test_module_entrypoint_forwards_arguments(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_main(args: list[str]) -> int:
        calls.append(args)
        return 0

    monkeypatch.setattr(sys, "argv", ["rclone_sync_manager", "doctor"])
    monkeypatch.setattr(__main__, "main", fake_main)

    assert __main__.run() == 0
    assert calls == [["doctor"]]
