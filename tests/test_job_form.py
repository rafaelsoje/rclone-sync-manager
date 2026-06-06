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

    assert dialog.windowTitle() == "Adicionar job"


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
