from pathlib import Path

from rclone_sync_manager.autostart import (
    DESKTOP_FILE_NAME,
    WINDOWS_AUTOSTART_FILE_NAME,
    autostart_file_path,
    desktop_file_content,
    is_desktop_autostart_enabled,
    set_desktop_autostart,
    windows_batch_content,
)


def test_autostart_file_path_uses_config_autostart(monkeypatch) -> None:
    monkeypatch.setattr("rclone_sync_manager.autostart.is_windows", lambda: False)

    assert autostart_file_path().name == DESKTOP_FILE_NAME
    assert autostart_file_path().parent.name == "autostart"


def test_desktop_file_content_opens_gui() -> None:
    content = desktop_file_content("/tmp/project venv/bin/python")

    assert 'Exec="/tmp/project venv/bin/python" -m rclone_sync_manager gui --start-hidden' in content
    assert "Terminal=false" in content


def test_set_desktop_autostart_creates_and_removes_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("rclone_sync_manager.autostart.is_windows", lambda: False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    path = set_desktop_autostart(True)

    assert path.exists()
    assert is_desktop_autostart_enabled()

    set_desktop_autostart(False)

    assert not path.exists()
    assert not is_desktop_autostart_enabled()


def test_windows_autostart_uses_startup_batch(tmp_path: Path, monkeypatch) -> None:
    startup = tmp_path / "Startup"
    monkeypatch.setattr("rclone_sync_manager.autostart.is_windows", lambda: True)
    monkeypatch.setattr("rclone_sync_manager.autostart.windows_startup_dir", lambda: startup)

    path = set_desktop_autostart(True)

    assert path == startup / WINDOWS_AUTOSTART_FILE_NAME
    assert path.exists()
    assert "rclone_sync_manager gui --start-hidden" in path.read_text(encoding="utf-8")


def test_windows_batch_content_opens_hidden_gui() -> None:
    content = windows_batch_content(r"C:\Project Venv\Scripts\python.exe")

    assert 'start "" /min "C:\\Project Venv\\Scripts\\python.exe" -m rclone_sync_manager gui --start-hidden' in content
