from rclone_sync_manager.runner import _friendly_error_message


def test_friendly_error_message_for_corrupted_transfer() -> None:
    message = _friendly_error_message("file.partial: corrupted on transfer")

    assert message is not None
    assert "Arquivo corrompido" in message


def test_friendly_error_message_for_permission_denied() -> None:
    message = _friendly_error_message("open C:\\dados: Access is denied")

    assert message is not None
    assert "Permissao negada" in message


def test_friendly_error_message_for_abusive_file() -> None:
    message = _friendly_error_message("Error 403: cannotDownloadAbusiveFile. Use the --drive-acknowledge-abuse flag")

    assert message is not None
    assert "drive-acknowledge-abuse" in message
    assert "Google Drive bloqueou" in message


def test_extract_last_error_from_log(tmp_path) -> None:
    from rclone_sync_manager.runner import _extract_last_error_from_log

    log_file = tmp_path / "test.log"
    log_file.write_text(
        "2026/09/30 11:00:00 NOTICE: Starting\n"
        "2026/09/30 11:00:01 ERROR : file.txt: failed to copy: 403\n"
        "2026/09/30 11:00:02 ERROR : Fatal error\n"
    )
    result = _extract_last_error_from_log(log_file)
    assert "ERROR : file.txt: failed to copy: 403" in result
    assert "ERROR : Fatal error" in result

