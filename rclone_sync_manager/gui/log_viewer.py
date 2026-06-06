from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
)

from ..config import ensure_app_dirs
from ..database import Database
from ..utils import safe_filename


class LogViewerDialog(QDialog):
    def __init__(self, parent=None, selected_job: str | None = None) -> None:
        super().__init__(parent)
        self.db = Database()
        self.paths = ensure_app_dirs()
        self.setWindowTitle("Logs")
        self.resize(900, 620)

        self.job_combo = QComboBox()
        self.error_only_check = QCheckBox("Erros")
        self.refresh_button = QPushButton("Atualizar")
        self.open_button = QPushButton("Abrir arquivo")
        self.clear_button = QPushButton("Limpar")
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)

        top = QHBoxLayout()
        top.addWidget(self.job_combo)
        top.addWidget(self.error_only_check)
        top.addWidget(self.refresh_button)
        top.addWidget(self.open_button)
        top.addWidget(self.clear_button)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.log_text)
        self.setLayout(layout)

        self.refresh_button.clicked.connect(self.refresh)
        self.open_button.clicked.connect(self.open_log_file)
        self.clear_button.clicked.connect(self.log_text.clear)
        self.error_only_check.toggled.connect(self.refresh)
        self.job_combo.currentTextChanged.connect(self.refresh)
        self._load_jobs(selected_job)
        self.refresh()

    def _load_jobs(self, selected_job: str | None) -> None:
        self.job_combo.clear()
        for job in self.db.list_jobs():
            self.job_combo.addItem(job.name)
        if selected_job:
            index = self.job_combo.findText(selected_job)
            if index >= 0:
                self.job_combo.setCurrentIndex(index)

    def refresh(self) -> None:
        job_name = self.job_combo.currentText()
        if not job_name:
            self.log_text.setPlainText("Nenhum job selecionado.")
            return
        log_file = self.paths.job_log_dir / f"{safe_filename(job_name)}.log"
        if not log_file.exists():
            self.log_text.setPlainText(f"Log ainda não existe:\n{log_file}")
            return
        text = _tail_text(log_file)
        if self.error_only_check.isChecked():
            lines = [line for line in text.splitlines() if "error" in line.lower()]
            text = "\n".join(lines)
        self.log_text.setPlainText(text)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def open_log_file(self) -> None:
        job_name = self.job_combo.currentText()
        if not job_name:
            return
        log_file = self.paths.job_log_dir / f"{safe_filename(job_name)}.log"
        if log_file.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_file)))


def _tail_text(path: Path, max_bytes: int = 160_000) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        return handle.read().decode("utf-8", errors="replace")
