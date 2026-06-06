from rclone_sync_manager.runner import _friendly_error_message


def test_friendly_error_message_for_corrupted_transfer() -> None:
    message = _friendly_error_message("file.partial: corrupted on transfer")

    assert message is not None
    assert "Arquivo corrompido" in message


def test_friendly_error_message_for_permission_denied() -> None:
    message = _friendly_error_message("open C:\\dados: Access is denied")

    assert message is not None
    assert "Permissao negada" in message
