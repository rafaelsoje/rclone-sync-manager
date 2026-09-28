import os

import pytest

from rclone_sync_manager.models import Job


def test_job_form_dialog_constructs() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    job_form = pytest.importorskip("rclone_sync_manager.gui.job_form")
    QApplication = widgets.QApplication
    JobFormDialog = job_form.JobFormDialog
    app = QApplication.instance() or QApplication([])
    dialog = JobFormDialog()

    assert dialog.windowTitle() == "Adicionar sincronização"


def test_new_job_runs_on_startup_and_after_save_by_default() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    job_form = pytest.importorskip("rclone_sync_manager.gui.job_form")
    QApplication = widgets.QApplication
    JobFormDialog = job_form.JobFormDialog
    app = QApplication.instance() or QApplication([])
    dialog = JobFormDialog()

    assert dialog.run_on_startup_check.isChecked()
    assert dialog.start_after_save()


def test_edit_job_keeps_saved_run_on_startup_value() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    job_form = pytest.importorskip("rclone_sync_manager.gui.job_form")
    QApplication = widgets.QApplication
    JobFormDialog = job_form.JobFormDialog
    app = QApplication.instance() or QApplication([])
    dialog = JobFormDialog(
        job=Job(
            name="Docs",
            local_path="/tmp/docs",
            remote_path="remote:docs",
            run_on_startup=False,
        )
    )

    assert not dialog.run_on_startup_check.isChecked()


def test_job_form_extra_flags() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    job_form = pytest.importorskip("rclone_sync_manager.gui.job_form")
    QApplication = widgets.QApplication
    JobFormDialog = job_form.JobFormDialog
    _ = QApplication.instance() or QApplication([])

    job = Job(
        name="DocsFlags",
        local_path="/tmp/docs",
        remote_path="drive:docs",
        extra_flags=["--fast-list", "--drive-skip-gdocs"],
    )
    dialog = JobFormDialog(job=job)
    assert dialog.extra_flags_edit.text() == "--fast-list --drive-skip-gdocs"

    dialog._append_extra_flag("--bwlimit 10M")
    assert "--bwlimit 10M" in dialog.extra_flags_edit.text()

    result = dialog.result_job()
    assert "--fast-list" in result.extra_flags
    assert "--drive-skip-gdocs" in result.extra_flags
    assert "--bwlimit" in result.extra_flags


def test_job_form_code_editor_sync() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    job_form = pytest.importorskip("rclone_sync_manager.gui.job_form")
    QApplication = widgets.QApplication
    JobFormDialog = job_form.JobFormDialog
    _ = QApplication.instance() or QApplication([])

    dialog = JobFormDialog()
    dialog.name_edit.setText("SyncTest")
    dialog.local_edit.setText("/tmp/local")
    dialog.remote_edit.setText("drive:remote")
    dialog.extra_flags_edit.setText("--fast-list")

    # Sync to code in JSON format
    dialog.code_format_combo.setCurrentText("JSON")
    dialog._sync_code_from_form()
    json_text = dialog.code_edit.toPlainText()
    assert "SyncTest" in json_text
    assert "--fast-list" in json_text

    # Edit code and apply back to form
    modified_json = json_text.replace("SyncTest", "SyncTestModified")
    dialog.code_edit.setPlainText(modified_json)
    assert dialog._apply_code_to_form() is True
    assert dialog.name_edit.text() == "SyncTestModified"

    # Sync to code in .CONF format
    dialog.code_format_combo.setCurrentText(".CONF (INI)")
    dialog._sync_code_from_form()
    conf_text = dialog.code_edit.toPlainText()
    assert "synctestmodified" in conf_text.lower()
    assert "drive:remote" in conf_text

