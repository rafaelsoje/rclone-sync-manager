from pathlib import Path

from rclone_sync_manager.systemd import SERVICE_NAME, installed_service_path, service_file_content


def test_installed_service_path_ends_with_service_name() -> None:
    assert installed_service_path().name == SERVICE_NAME


def test_service_file_content_uses_python_module_entrypoint() -> None:
    content = service_file_content("/tmp/project venv/bin/python")

    assert 'ExecStart="/tmp/project venv/bin/python" -m rclone_sync_manager start' in content
