import subprocess

from rclone_sync_manager.rclone_utils import (
    _popen_terminal,
    _terminal_command,
    delete_remote,
    join_remote_path,
    list_remote_entries,
    list_remote_entries_result,
    remote_name,
    split_remote_path,
)


def test_remote_name() -> None:
    assert remote_name("dropbox:Exc") == "dropbox"
    assert remote_name("drive:Folder/Sub") == "drive"
    assert remote_name("/local/path") is None
    assert remote_name(":bad") is None


def test_split_and_join_remote_path() -> None:
    assert split_remote_path("dropbox:Exc/Sub") == ("dropbox", "Exc/Sub")
    assert split_remote_path("bad") == ("", "")
    assert join_remote_path("dropbox", "Exc/Sub") == "dropbox:Exc/Sub"
    assert join_remote_path("dropbox:", "") == "dropbox:"


def test_list_remote_entries(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="Folder/\nfile.txt\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    entries = list_remote_entries("dropbox:Root")

    assert entries[0].is_dir
    assert entries[0].path == "dropbox:Root/Folder"
    assert not entries[1].is_dir
    assert entries[1].path == "dropbox:Root/file.txt"


def test_list_remote_entries_result_reports_error(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = list_remote_entries_result("dropbox:Root")

    assert result.entries == []
    assert result.error == "boom"


def test_delete_remote_calls_rclone_config_delete(monkeypatch) -> None:
    calls = []

    def fake_run(args, check, capture_output, text, timeout):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="deleted", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, output = delete_remote("drive:", "rclone")

    assert ok
    assert output == "deleted"
    assert calls == [["rclone", "config", "delete", "drive:"]]


def test_terminal_command_prefers_available_terminal(monkeypatch) -> None:
    monkeypatch.setattr("rclone_sync_manager.rclone_utils.is_windows", lambda: False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/konsole" if name == "konsole" else None)

    command = _terminal_command(["rclone", "config"])

    assert command == ["konsole", "-e", "rclone", "config"]


def test_terminal_command_uses_cmd_on_windows(monkeypatch) -> None:
    monkeypatch.setattr("rclone_sync_manager.rclone_utils.is_windows", lambda: True)

    command = _terminal_command(["rclone", "config"])

    assert command == ["cmd.exe", "/k", "rclone config"]


def test_open_terminal_creates_new_console_on_windows(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("rclone_sync_manager.rclone_utils.is_windows", lambda: True)
    monkeypatch.setattr(subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)

    class FakePopen:
        def __init__(self, command, **kwargs):
            calls.append((command, kwargs))

    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    _popen_terminal(["cmd.exe", "/k", "rclone config"])

    assert calls == [(["cmd.exe", "/k", "rclone config"], {"creationflags": 16})]
