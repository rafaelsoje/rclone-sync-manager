from rclone_sync_manager.utils import safe_filename


def test_safe_filename() -> None:
    assert safe_filename("Meus Documentos:/") == "Meus_Documentos"
