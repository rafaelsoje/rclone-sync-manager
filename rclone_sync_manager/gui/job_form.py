from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_IGNORE_PATTERNS
from ..models import Job
from ..rclone_utils import join_remote_path, list_remotes, remote_exists, remote_name, split_remote_path
from .remote_browser import RemoteBrowserDialog


class JobFormDialog(QDialog):
    def __init__(self, parent=None, job: Job | None = None) -> None:
        super().__init__(parent)
        self.job = job
        self.setWindowTitle("Editar job" if job else "Adicionar job")
        self.resize(640, 620)

        self.name_edit = QLineEdit()
        self.local_edit = QLineEdit()
        self.remote_edit = QLineEdit()
        self.remote_combo = QComboBox()
        self.remote_path_edit = QLineEdit()
        self.remote_path_edit.setPlaceholderText("Documentos/Subpasta")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["copy", "sync", "bisync"])
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("Local -> Remote", "local_to_remote")
        self.direction_combo.addItem("Remote -> Local", "remote_to_local")
        self.realtime_check = QCheckBox()
        self.run_on_startup_check = QCheckBox()
        self.run_on_startup_check.setChecked(job is None)
        self.schedule_check = QCheckBox()
        self.schedule_edit = QLineEdit()
        self.schedule_edit.setPlaceholderText("02:00")
        self.debounce_spin = QSpinBox()
        self.debounce_spin.setRange(6, 86400)
        self.debounce_spin.setValue(30)
        self.transfers_spin = QSpinBox()
        self.transfers_spin.setRange(1, 128)
        self.transfers_spin.setValue(4)
        self.checkers_spin = QSpinBox()
        self.checkers_spin.setRange(1, 128)
        self.checkers_spin.setValue(8)
        self.performance_combo = QComboBox()
        self.performance_combo.addItems(["Manual", "Padrão", "Rápido", "Agressivo"])
        self.performance_combo.setCurrentText("Padrão")
        self.bwlimit_combo = QComboBox()
        self.bwlimit_combo.setEditable(True)
        self.bwlimit_combo.addItems(["Sem limite", "512K", "1M", "2M", "5M", "10M", "20M", "50M", "100M"])
        self.bwlimit_combo.setCurrentIndex(0)
        if self.bwlimit_combo.lineEdit() is not None:
            self.bwlimit_combo.lineEdit().setPlaceholderText("Ex: 2M")
        self.dry_run_check = QCheckBox()
        self.priority_check = QCheckBox()
        self.priority_check.setChecked(True)
        self.notify_check = QCheckBox()
        self.notify_check.setChecked(True)
        self.start_after_save_check = QCheckBox("Iniciar sincronização ao salvar")
        self.start_after_save_check.setChecked(True)
        self.include_edit = QTextEdit()
        self.include_edit.setPlaceholderText("Opcional: padrões a baixar, ex: media/all/**")
        self.ignore_enabled_check = QCheckBox("Habilitar")
        self.ignore_edit = QTextEdit()
        self.ignore_edit.setEnabled(False)
        self.ignore_edit.setPlaceholderText("Desabilitado por padrão. Marque Habilitar para usar filtros.")

        browse_button = QPushButton("Escolher")
        browse_button.clicked.connect(self._browse_local_path)
        local_row = QHBoxLayout()
        local_row.addWidget(self.local_edit)
        local_row.addWidget(browse_button)

        browse_remote_button = QPushButton("Navegar")
        browse_remote_button.clicked.connect(self._browse_remote_path)
        include_remote_button = QPushButton("Incluir itens")
        include_remote_button.clicked.connect(self._browse_remote_includes)
        ignore_remote_button = QPushButton("Ignorar itens")
        ignore_remote_button.clicked.connect(self._browse_remote_ignores)
        self._load_remote_combo()
        remote_row = QHBoxLayout()
        remote_row.addWidget(self.remote_combo)
        remote_row.addWidget(self.remote_path_edit)
        remote_row.addWidget(browse_remote_button)

        tabs = QTabWidget()

        basic_tab = QWidget()
        basic_form = QFormLayout()
        basic_form.addRow("Nome do job", self.name_edit)
        basic_form.addRow("Pasta local", local_row)
        basic_form.addRow("Selecionar remote", remote_row)
        basic_form.addRow("Remote rclone", self.remote_edit)
        basic_form.addRow("Modo", self.mode_combo)
        basic_form.addRow("Direção", self.direction_combo)
        basic_tab.setLayout(basic_form)

        execution_tab = QWidget()
        execution_form = QFormLayout()
        execution_form.addRow("Ativar realtime", self.realtime_check)
        execution_form.addRow("Executar ao iniciar", self.run_on_startup_check)
        execution_form.addRow("Ativar agendamento", self.schedule_check)
        execution_form.addRow("Horário", self.schedule_edit)
        execution_form.addRow("Debounce em segundos", self.debounce_spin)
        execution_form.addRow("Perfil de performance", self.performance_combo)
        execution_form.addRow("Transfers", self.transfers_spin)
        execution_form.addRow("Checkers", self.checkers_spin)
        execution_form.addRow("Limite de banda", self.bwlimit_combo)
        if job is None:
            execution_form.addRow("Ao salvar", self.start_after_save_check)
        execution_tab.setLayout(execution_form)

        advanced_tab = QWidget()
        advanced_form = QFormLayout()
        advanced_form.addRow("Dry-run", self.dry_run_check)
        advanced_form.addRow("Prioridade baixa", self.priority_check)
        advanced_form.addRow("Notificações", self.notify_check)
        advanced_tab.setLayout(advanced_form)

        filters_tab = QWidget()
        filters_layout = QVBoxLayout()
        include_row = QHBoxLayout()
        include_row.addWidget(QLabel("Padrões incluídos"))
        include_row.addWidget(include_remote_button)
        filters_layout.addLayout(include_row)
        filters_layout.addWidget(self.include_edit)
        ignore_row = QHBoxLayout()
        ignore_row.addWidget(QLabel("Padrões ignorados"))
        ignore_row.addWidget(self.ignore_enabled_check)
        ignore_row.addWidget(ignore_remote_button)
        filters_layout.addLayout(ignore_row)
        filters_layout.addWidget(self.ignore_edit)
        filters_tab.setLayout(filters_layout)

        tabs.addTab(basic_tab, "Básico")
        tabs.addTab(execution_tab, "Execução")
        tabs.addTab(filters_tab, "Filtros")
        tabs.addTab(advanced_tab, "Avançado")

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        _clear_button_icons(buttons)
        buttons.accepted.connect(self._accept_with_validation)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        self.setLayout(layout)

        self.schedule_check.toggled.connect(self.schedule_edit.setEnabled)
        self.schedule_edit.setEnabled(False)
        self.mode_combo.currentTextChanged.connect(self._mode_changed)
        self.direction_combo.currentIndexChanged.connect(self._direction_changed)
        self.remote_combo.currentTextChanged.connect(self._sync_remote_edit_from_parts)
        self.remote_path_edit.textChanged.connect(self._sync_remote_edit_from_parts)
        self.remote_edit.textChanged.connect(self._sync_remote_parts_from_edit)
        self.ignore_enabled_check.toggled.connect(self._toggle_ignore_patterns)
        self.performance_combo.currentTextChanged.connect(self._apply_performance_profile)

        if job:
            self._load_job(job)
        self._mode_changed(self.mode_combo.currentText())

    def start_after_save(self) -> bool:
        return self.job is None and self.start_after_save_check.isChecked()

    def result_job(self) -> Job:
        schedule_time = self.schedule_edit.text().strip() if self.schedule_check.isChecked() else None
        patterns = [line.strip() for line in self.ignore_edit.toPlainText().splitlines() if line.strip()]
        include_patterns = [line.strip() for line in self.include_edit.toPlainText().splitlines() if line.strip()]
        return Job(
            id=self.job.id if self.job else None,
            name=self.name_edit.text().strip(),
            enabled=self.job.enabled if self.job else True,
            run_on_startup=self.run_on_startup_check.isChecked(),
            local_path=str(Path(self.local_edit.text().strip()).expanduser()),
            remote_path=self.remote_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            direction=self.direction_combo.currentData(),
            realtime=self.realtime_check.isChecked(),
            schedule_time=schedule_time,
            debounce_seconds=self.debounce_spin.value(),
            transfers=self.transfers_spin.value(),
            checkers=self.checkers_spin.value(),
            bandwidth_limit=self._bandwidth_limit_value(),
            dry_run=self.dry_run_check.isChecked(),
            priority_low=self.priority_check.isChecked(),
            notify=self.notify_check.isChecked(),
            ignore_patterns=patterns,
            include_patterns=include_patterns,
            created_at=self.job.created_at if self.job else None,
            updated_at=self.job.updated_at if self.job else None,
        )

    def _load_job(self, job: Job) -> None:
        self.name_edit.setText(job.name)
        self.local_edit.setText(job.local_path)
        self.remote_edit.setText(job.remote_path)
        self._sync_remote_parts_from_edit(job.remote_path)
        self.mode_combo.setCurrentText(job.mode)
        self.direction_combo.setCurrentIndex(
            max(0, self.direction_combo.findData(job.direction))
        )
        self.realtime_check.setChecked(job.realtime)
        self.run_on_startup_check.setChecked(job.run_on_startup)
        self.schedule_check.setChecked(bool(job.schedule_time))
        self.schedule_edit.setText(job.schedule_time or "")
        self.schedule_edit.setEnabled(bool(job.schedule_time))
        self.debounce_spin.setValue(job.debounce_seconds)
        self.transfers_spin.setValue(job.transfers)
        self.checkers_spin.setValue(job.checkers)
        self.performance_combo.setCurrentText("Manual")
        self.bwlimit_combo.setCurrentText(job.bandwidth_limit or "Sem limite")
        self.dry_run_check.setChecked(job.dry_run)
        self.priority_check.setChecked(job.priority_low)
        self.notify_check.setChecked(job.notify)
        self.include_edit.setPlainText("\n".join(job.include_patterns))
        self.ignore_enabled_check.setChecked(bool(job.ignore_patterns))
        self.ignore_edit.setPlainText("\n".join(job.ignore_patterns))
        self.ignore_edit.setEnabled(bool(job.ignore_patterns))

    def _browse_local_path(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Selecionar pasta local", self.local_edit.text())
        if directory:
            self.local_edit.setText(directory)

    def _browse_remote_path(self) -> None:
        dialog = RemoteBrowserDialog(self, self.remote_edit.text().strip())
        if dialog.exec() == RemoteBrowserDialog.Accepted:
            self.remote_edit.setText(dialog.selected_path)

    def _browse_remote_includes(self) -> None:
        dialog = RemoteBrowserDialog(self, self.remote_edit.text().strip())
        if dialog.exec() != RemoteBrowserDialog.Accepted:
            return
        self._merge_patterns_from_remote(dialog, self.include_edit)

    def _browse_remote_ignores(self) -> None:
        if not self.ignore_enabled_check.isChecked():
            self.ignore_enabled_check.setChecked(True)
        dialog = RemoteBrowserDialog(self, self.remote_edit.text().strip())
        if dialog.exec() != RemoteBrowserDialog.Accepted:
            return
        self._merge_patterns_from_remote(dialog, self.ignore_edit)

    def _merge_patterns_from_remote(self, dialog: RemoteBrowserDialog, target: QTextEdit) -> None:
        existing = [line.strip() for line in target.toPlainText().splitlines() if line.strip()]
        additions = [
            _remote_entry_to_exclude_pattern(entry.path, self.remote_edit.text().strip(), entry.is_dir)
            for entry in dialog.selected_entries
        ]
        if not additions and dialog.selected_path:
            additions = [_remote_entry_to_exclude_pattern(dialog.selected_path, self.remote_edit.text().strip(), True)]
        merged = existing + [pattern for pattern in additions if pattern and pattern not in existing]
        target.setPlainText("\n".join(merged))

    def _accept_with_validation(self) -> None:
        try:
            job = self.result_job()
            self._validate(job)
        except ValueError as exc:
            QMessageBox.warning(self, "Dados inválidos", str(exc))
            return

        if job.mode == "sync":
            source = job.remote_path if job.direction == "remote_to_local" else job.local_path
            destination = job.local_path if job.direction == "remote_to_local" else job.remote_path
            if QMessageBox.warning(
                self,
                "Confirmar modo sync",
                "O modo sync espelha a origem e pode apagar arquivos no destino.\n\n"
                f"Origem: {source}\n"
                f"Destino: {destination}",
                QMessageBox.Cancel | QMessageBox.Ok,
                QMessageBox.Cancel,
            ) != QMessageBox.Ok:
                return
        if job.mode == "bisync":
            if QMessageBox.warning(
                self,
                "Confirmar modo bisync",
                "O primeiro bisync precisa ser inicializado manualmente com --resync antes de rodar automaticamente.",
                QMessageBox.Cancel | QMessageBox.Ok,
                QMessageBox.Cancel,
            ) != QMessageBox.Ok:
                return
        self.accept()

    def _validate(self, job: Job) -> None:
        if not job.name:
            raise ValueError("Nome obrigatório.")
        local_path = Path(job.local_path)
        if job.direction == "remote_to_local":
            try:
                local_path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ValueError(f"Nao foi possivel criar a pasta local: {exc}") from exc
        if not local_path.is_dir():
            raise ValueError("A pasta local precisa existir e ser uma pasta.")
        if not job.remote_path:
            raise ValueError("Remote rclone obrigatório.")
        name = remote_name(job.remote_path)
        if not name:
            raise ValueError("Remote rclone precisa estar no formato remote:pasta.")
        if not remote_exists(job.remote_path):
            remotes = ", ".join(f"{remote}:" for remote in list_remotes()) or "nenhum remote encontrado"
            raise ValueError(f"Remote não encontrado: {name}:. Remotes disponíveis: {remotes}")
        if self.schedule_check.isChecked() and not _valid_hhmm(job.schedule_time or ""):
            raise ValueError("Use um horário no formato HH:MM.")
        if job.mode == "bisync" and job.direction != "local_to_remote":
            raise ValueError("Bisync é bidirecional; deixe a direção como Local -> Remote.")
    def _mode_changed(self, mode: str) -> None:
        is_bisync = mode == "bisync"
        if is_bisync:
            self.direction_combo.setCurrentIndex(0)
        self.direction_combo.setEnabled(not is_bisync)
        self._direction_changed()

    def _direction_changed(self) -> None:
        self.realtime_check.setEnabled(True)

    def _toggle_ignore_patterns(self, enabled: bool) -> None:
        self.ignore_edit.setEnabled(enabled)
        if enabled and not self.ignore_edit.toPlainText().strip():
            self.ignore_edit.setPlainText("\n".join(DEFAULT_IGNORE_PATTERNS))
        if not enabled:
            self.ignore_edit.clear()

    def _apply_performance_profile(self, profile: str) -> None:
        profiles = {
            "Padrão": (4, 8, "Sem limite"),
            "Rápido": (8, 16, "Sem limite"),
            "Agressivo": (12, 24, "Sem limite"),
        }
        if profile not in profiles:
            return
        transfers, checkers, bandwidth = profiles[profile]
        self.transfers_spin.setValue(transfers)
        self.checkers_spin.setValue(checkers)
        self.bwlimit_combo.setCurrentText(bandwidth)

    def _bandwidth_limit_value(self) -> str | None:
        value = self.bwlimit_combo.currentText().strip()
        if not value or value == "Sem limite":
            return None
        return value

    def _load_remote_combo(self) -> None:
        self.remote_combo.blockSignals(True)
        self.remote_combo.clear()
        for remote in list_remotes():
            self.remote_combo.addItem(f"{remote}:")
        self.remote_combo.blockSignals(False)

    def _sync_remote_edit_from_parts(self) -> None:
        remote = self.remote_combo.currentText().rstrip(":")
        if not remote:
            return
        self.remote_edit.blockSignals(True)
        self.remote_edit.setText(join_remote_path(remote, self.remote_path_edit.text()))
        self.remote_edit.blockSignals(False)

    def _sync_remote_parts_from_edit(self, value: str) -> None:
        remote, path = split_remote_path(value)
        if not remote:
            return
        self.remote_combo.blockSignals(True)
        self.remote_path_edit.blockSignals(True)
        index = self.remote_combo.findText(f"{remote}:")
        if index >= 0:
            self.remote_combo.setCurrentIndex(index)
        self.remote_path_edit.setText(path)
        self.remote_combo.blockSignals(False)
        self.remote_path_edit.blockSignals(False)


def _valid_hhmm(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2:
        return False
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59


def _remote_entry_to_exclude_pattern(remote_path: str, base_remote_path: str, is_dir: bool) -> str:
    remote, selected_path = split_remote_path(remote_path)
    base_remote, base_path = split_remote_path(base_remote_path)
    if remote == base_remote and base_path and selected_path.startswith(f"{base_path}/"):
        relative = selected_path[len(base_path) + 1 :]
    elif remote == base_remote and selected_path == base_path:
        relative = selected_path.rsplit("/", 1)[-1] if selected_path else ""
    else:
        relative = selected_path
    relative = relative.strip("/")
    if not relative:
        return ""
    return f"{relative}/**" if is_dir else relative


def _clear_button_icons(buttons: QDialogButtonBox) -> None:
    for button in buttons.buttons():
        button.setIcon(button.icon().__class__())
