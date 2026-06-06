from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..database import Database
from ..config import ensure_app_dirs
from ..jobs_io import export_jobs, import_jobs
from ..lock_manager import LockManager
from ..models import Job, JobStatus
from ..progress import progress_snapshot_from_log
from ..runner import RcloneRunner
from ..utils import safe_filename, shell_join
from .doctor_dialog import DoctorDialog
from .job_form import JobFormDialog
from .log_viewer import LogViewerDialog
from .remote_browser import RemoteBrowserDialog
from .settings_dialog import SettingsDialog


class RunJobThread(QThread):
    finished_run = Signal(str, int, str)

    def __init__(self, job: Job, db: Database, resync: bool = False) -> None:
        super().__init__()
        self.job = job
        self.db = db
        self.resync = resync

    def run(self) -> None:
        try:
            rclone_path = self.db.get_setting("rclone_path", "rclone") or "rclone"
            result = RcloneRunner(db=self.db, rclone_path=rclone_path).run(self.job, resync=self.resync)
            detail = f"{shell_join(result.command)}\n\nLog: {result.log_file}"
            if result.error_message:
                detail = f"{detail}\n\n{result.error_message}"
            self.finished_run.emit(self.job.name, result.exit_code, detail)
        except Exception as exc:
            self.finished_run.emit(self.job.name, 1, str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.db = Database()
        self.db.initialize()
        self.locks = LockManager()
        self.locks.cleanup_stale_locks()
        self._reconcile_runtime_state()
        self._threads: list[RunJobThread] = []
        self._refreshing = False
        self._all_jobs: list[Job] = []

        self.setWindowTitle("Rclone Sync Manager")
        self.resize(1360, 760)
        self._restore_window_geometry()

        self.table = QTableWidget(0, 9)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setHorizontalHeaderLabels(
            [
                "Nome",
                "Pasta local",
                "Remoto",
                "Modo",
                "Realtime",
                "Agendamento",
                "Status",
                "Última execução",
                "Último resultado",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.customContextMenuRequested.connect(self._open_job_context_menu)

        self.detail_name = QLabel("-")
        self.detail_status = QLabel("-")
        self.detail_local = QLabel("-")
        self.detail_remote = QLabel("-")
        self.detail_mode = QLabel("-")
        self.detail_direction = QLabel("-")
        self.detail_realtime = QLabel("-")
        self.detail_run_on_startup = QLabel("-")
        self.detail_schedule = QLabel("-")
        self.detail_limits = QLabel("-")
        self.detail_activity = QLabel("-")
        self.detail_log_updated = QLabel("-")
        self.detail_progress_text = QLabel("-")
        self.detail_progress_text.setWordWrap(True)
        self.detail_progress_text.setMaximumWidth(620)
        self.activity_progress = QProgressBar()
        self.activity_progress.setTextVisible(False)
        self.activity_progress.setFixedHeight(14)
        self.detail_updated = QLabel("-")
        self.detail_last_error = QLabel("-")
        self.detail_last_error.setWordWrap(True)

        details_group = QGroupBox("Detalhes")
        details_form = QFormLayout()
        details_form.addRow("Nome", self.detail_name)
        details_form.addRow("Status", self.detail_status)
        details_form.addRow("Pasta local", self.detail_local)
        details_form.addRow("Remoto", self.detail_remote)
        details_form.addRow("Modo", self.detail_mode)
        details_form.addRow("Direção", self.detail_direction)
        details_form.addRow("Realtime", self.detail_realtime)
        details_form.addRow("Ao iniciar", self.detail_run_on_startup)
        details_form.addRow("Agendamento", self.detail_schedule)
        details_form.addRow("Limites", self.detail_limits)
        details_form.addRow("Atividade", self.detail_activity)
        details_form.addRow("Progresso", self.activity_progress)
        details_form.addRow("Andamento", self.detail_progress_text)
        details_form.addRow("Log atualizado", self.detail_log_updated)
        details_form.addRow("Atualizado", self.detail_updated)
        details_form.addRow("Último erro", self.detail_last_error)
        details_group.setLayout(details_form)

        self.history_table = QTableWidget(0, 6)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setHorizontalHeaderLabels(
            ["Início", "Fim", "Status", "Exit", "Duração", "Log"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        history_group = QGroupBox("Histórico")
        history_layout = QVBoxLayout()
        history_layout.addWidget(self.history_table)
        history_group.setLayout(history_layout)

        self.recent_log_text = QPlainTextEdit()
        self.recent_log_text.setReadOnly(True)
        self.recent_log_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        recent_log_group = QGroupBox("Log recente")
        recent_log_layout = QVBoxLayout()
        recent_log_layout.addWidget(self.recent_log_text)
        recent_log_group.setLayout(recent_log_layout)

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(details_group, "Detalhes")
        self.right_tabs.addTab(history_group, "Histórico")
        self.right_tabs.addTab(recent_log_group, "Log")

        self.add_button = QPushButton("Adicionar job")
        self.edit_button = QPushButton("Editar job")
        self.remove_button = QPushButton("Remover job")
        self.pause_button = QPushButton("Pausar")
        self.resume_button = QPushButton("Retomar")
        self.stop_button = QPushButton("Parar")
        self.run_button = QPushButton("Sincronizar agora")
        self.logs_button = QPushButton("Ver logs")
        self.diagnostics_button = QPushButton("Copiar diagnostico")
        self.doctor_button = QPushButton("Doctor")
        self.settings_button = QPushButton("Configurações")
        self.export_button = QPushButton("Exportar")
        self.import_button = QPushButton("Importar")
        self.refresh_button = QPushButton("Atualizar")
        self.auto_refresh_check = QCheckBox("Auto-refresh")
        self.auto_refresh_check.setChecked(True)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar job...")
        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems(["Todos", "Rodando", "Erro", "Pausados", "Parados", "Sucesso", "Idle"])
        self.summary_label = QLabel("Jobs: 0 | Rodando: 0 | Erros: 0 | Auto-refresh ativo")

        self.add_button.clicked.connect(self.add_job)
        self.edit_button.clicked.connect(self.edit_job)
        self.remove_button.clicked.connect(self.remove_job)
        self.pause_button.clicked.connect(self.pause_job)
        self.resume_button.clicked.connect(self.resume_job)
        self.stop_button.clicked.connect(self.stop_job)
        self.run_button.clicked.connect(self.run_selected_job)
        self.logs_button.clicked.connect(self.open_logs)
        self.diagnostics_button.clicked.connect(self.copy_diagnostics)
        self.doctor_button.clicked.connect(self.open_doctor)
        self.settings_button.clicked.connect(self.open_settings)
        self.export_button.clicked.connect(self.export_jobs_file)
        self.import_button.clicked.connect(self.import_jobs_file)
        self.refresh_button.clicked.connect(self.refresh)
        self.auto_refresh_check.toggled.connect(self._set_auto_refresh)
        self.search_edit.textChanged.connect(self.refresh)
        self.status_filter_combo.currentTextChanged.connect(self.refresh)

        button_row = QHBoxLayout()
        job_group = QGroupBox("Jobs")
        job_buttons = QHBoxLayout()
        for button in (self.add_button, self.edit_button, self.remove_button):
            job_buttons.addWidget(button)
        job_group.setLayout(job_buttons)
        execution_group = QGroupBox("Execução")
        execution_buttons = QHBoxLayout()
        for button in (self.run_button, self.pause_button, self.resume_button, self.stop_button):
            execution_buttons.addWidget(button)
        execution_group.setLayout(execution_buttons)
        tools_group = QGroupBox("Ferramentas")
        tools_buttons = QHBoxLayout()
        for button in (
            self.logs_button,
            self.diagnostics_button,
            self.doctor_button,
            self.settings_button,
            self.export_button,
            self.import_button,
            self.refresh_button,
        ):
            tools_buttons.addWidget(button)
        tools_group.setLayout(tools_buttons)
        button_row.addWidget(job_group)
        button_row.addWidget(execution_group)
        button_row.addWidget(tools_group)
        button_row.addWidget(self.auto_refresh_check)
        button_row.addStretch()

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtro"))
        filter_row.addWidget(self.search_edit, 1)
        filter_row.addWidget(QLabel("Status"))
        filter_row.addWidget(self.status_filter_combo)

        self.empty_label = QLabel("Nenhum job configurado")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.empty_add_button = QPushButton("Adicionar primeiro job")
        self.empty_add_button.clicked.connect(self.add_job)
        empty_layout = QVBoxLayout()
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_label)
        empty_layout.addWidget(self.empty_add_button, alignment=Qt.AlignCenter)
        empty_layout.addStretch()
        empty_page = QWidget()
        empty_page.setLayout(empty_layout)

        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(self.table)
        self.table_stack.addWidget(empty_page)

        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.addWidget(self.right_tabs, 1)
        right_panel.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(self.table_stack)
        splitter.addWidget(right_panel)
        splitter.setSizes([850, 510])

        layout = QVBoxLayout()
        layout.addLayout(button_row)
        layout.addLayout(filter_row)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.summary_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()
        self.refresh()

    def closeEvent(self, event) -> None:
        self._save_window_geometry()
        super().closeEvent(event)

    def refresh(self) -> None:
        self.locks.cleanup_stale_locks()
        self._reconcile_runtime_state()
        selected_name = self.selected_job_name()
        self._refreshing = True
        jobs = self.db.list_jobs()
        self._all_jobs = jobs
        filtered_jobs = [job for job in jobs if self._job_matches_filters(job)]
        self.table_stack.setCurrentIndex(0 if filtered_jobs else 1)
        if not jobs:
            self.empty_label.setText("Nenhum job configurado")
            self.empty_add_button.setText("Adicionar primeiro job")
        else:
            self.empty_label.setText("Nenhum job encontrado")
            self.empty_add_button.setText("Adicionar job")
        self.table.setRowCount(len(filtered_jobs))
        selected_restored = False
        for row, job in enumerate(filtered_jobs):
            last_run = self.db.get_last_job_run(job.id) if job.id is not None else None
            runtime_status = self.db.get_job_status_text(job.id) if job.id is not None else "idle"
            status = "paused" if not job.enabled else runtime_status
            values = [
                job.name,
                job.local_path,
                job.remote_path,
                job.mode,
                "sim" if job.realtime else "não",
                job.schedule_time or "-",
                status,
                last_run["finished_at"] if last_run and last_run["finished_at"] else "-",
                _format_last_result(last_run),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                _apply_status_color(item, status)
                if column == 6:
                    item.setText(_format_status_label(status))
                if column == 0 and job.id is not None:
                    item.setData(256, job.id)
                self.table.setItem(row, column, item)
            if selected_name and job.name == selected_name:
                self.table.selectRow(row)
                selected_restored = True
        if filtered_jobs and not selected_restored:
            self.table.selectRow(0)
        self._refreshing = False
        self._update_summary(jobs)
        self._update_buttons()
        self._update_details()

    def add_job(self) -> None:
        dialog = JobFormDialog(self)
        if dialog.exec() != JobFormDialog.Accepted:
            return
        try:
            created_job = self.db.create_job(dialog.result_job())
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível criar", str(exc))
            return
        self.refresh()
        if dialog.start_after_save():
            self._start_job_thread(created_job)

    def edit_job(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        dialog = JobFormDialog(self, job)
        if dialog.exec() != JobFormDialog.Accepted:
            return
        try:
            self.db.update_job(dialog.result_job())
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível salvar", str(exc))
            return
        self.refresh()

    def remove_job(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        if QMessageBox.question(
            self,
            "Remover job",
            f"Remover o job {job.name}?",
            QMessageBox.Cancel | QMessageBox.Yes,
            QMessageBox.Cancel,
        ) != QMessageBox.Yes:
            return
        if self.locks.is_locked(job):
            self.locks.stop_job(job)
        else:
            self.locks.remove_lock(job)
        self.db.delete_job(job.name)
        self.refresh()

    def pause_job(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        self.db.set_job_enabled(job.name, False)
        self.refresh()

    def resume_job(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        self.db.set_job_enabled(job.name, True)
        self.refresh()

    def stop_job(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        if self.locks.stop_job(job):
            if job.id is not None:
                self.db.set_job_status(job.id, JobStatus.STOPPED.value, "parada solicitada pelo usuário")
            self.refresh()
            QMessageBox.information(self, "Parar job", f"Foi solicitado parar {job.name}.")
            return
        self.locks.remove_lock(job)
        self.refresh()
        QMessageBox.information(self, "Parar job", f"{job.name} não parece estar rodando.")

    def quit_app(self) -> None:
        running_jobs = [job for job in self.db.list_jobs() if self.locks.is_locked(job)]
        if running_jobs:
            names = ", ".join(job.name for job in running_jobs)
            answer = QMessageBox.question(
                self,
                "Sair",
                f"Existem jobs rodando: {names}.\n\nDeseja parar esses jobs e sair?",
                QMessageBox.Cancel | QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Cancel:
                return
            if answer == QMessageBox.Yes:
                for job in running_jobs:
                    self.locks.stop_job(job)
                    if job.id is not None:
                        self.db.set_job_status(job.id, JobStatus.STOPPED.value, "parada solicitada ao sair")
            if answer == QMessageBox.No:
                QApplication.instance().quit()
                return
        QApplication.instance().quit()

    def run_selected_job(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        self._run_job_with_confirmations(job)

    def run_all_jobs(self) -> None:
        for job in self.db.list_jobs():
            if job.enabled:
                self._start_job_thread(job)

    def pause_all_jobs(self) -> None:
        for job in self.db.list_jobs():
            self.db.set_job_enabled(job.name, False)
        self.refresh()

    def resume_all_jobs(self) -> None:
        for job in self.db.list_jobs():
            self.db.set_job_enabled(job.name, True)
        self.refresh()

    def _run_job_with_confirmations(self, job: Job) -> None:
        if job.mode == "sync":
            source = job.remote_path if job.direction == "remote_to_local" else job.local_path
            destination = job.local_path if job.direction == "remote_to_local" else job.remote_path
            destination_note = ""
            if job.direction == "remote_to_local" and _local_directory_has_entries(job.local_path):
                destination_note = "\n\nA pasta local de destino ja contem arquivos."
            if QMessageBox.warning(
                self,
                "Confirmar sync",
                "O modo sync espelha a origem e pode apagar arquivos no destino.\n\n"
                f"Origem: {source}\n"
                f"Destino: {destination}"
                f"{destination_note}",
                QMessageBox.Cancel | QMessageBox.Ok,
                QMessageBox.Cancel,
            ) != QMessageBox.Ok:
                return
        if job.mode == "bisync":
            if QMessageBox.warning(
                self,
                "Bisync",
                "Use rsm init-bisync --job no terminal para a primeira execução com --resync.",
                QMessageBox.Cancel | QMessageBox.Ok,
                QMessageBox.Cancel,
            ) != QMessageBox.Ok:
                return
        self._start_job_thread(job)

    def _start_job_thread(self, job: Job) -> None:
        self.run_button.setEnabled(False)
        if job.id is not None:
            self.db.set_job_status(job.id, JobStatus.RUNNING.value)
        self.refresh()
        thread = RunJobThread(job, self.db)
        thread.finished_run.connect(self._job_run_finished)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        self._threads.append(thread)
        thread.start()

    def open_logs(self) -> None:
        job = self.selected_job()
        dialog = LogViewerDialog(self, job.name if job else None)
        dialog.exec()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def open_doctor(self) -> None:
        dialog = DoctorDialog(self)
        dialog.exec()

    def export_jobs_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar jobs",
            "rclone-sync-manager-jobs.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            count = export_jobs(self.db, path)
        except Exception as exc:
            QMessageBox.warning(self, "Exportar jobs", str(exc))
            return
        QMessageBox.information(self, "Exportar jobs", f"{count} job(s) exportado(s).")

    def import_jobs_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar jobs", "", "JSON (*.json)")
        if not path:
            return
        try:
            count = import_jobs(self.db, path, overwrite=True)
        except Exception as exc:
            QMessageBox.warning(self, "Importar jobs", str(exc))
            return
        self.refresh()
        QMessageBox.information(self, "Importar jobs", f"{count} job(s) importado(s).")

    def open_local_folder(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(job.local_path)):
            QMessageBox.warning(self, "Abrir pasta local", f"Não foi possível abrir {job.local_path}.")

    def browse_selected_remote(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        dialog = RemoteBrowserDialog(self, job.remote_path)
        dialog.exec()

    def copy_rclone_command(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        rclone_path = self.db.get_setting("rclone_path", "rclone") or "rclone"
        command, _ = RcloneRunner(db=self.db, rclone_path=rclone_path).build_command(job)
        QApplication.clipboard().setText(shell_join(command))
        QMessageBox.information(self, "Comando rclone", "Comando copiado para a área de transferência.")

    def copy_diagnostics(self) -> None:
        job = self.selected_job()
        if job is None:
            return
        QApplication.clipboard().setText(self._diagnostics_text(job))
        QMessageBox.information(self, "Diagnostico", "Diagnostico copiado para a area de transferencia.")

    def selected_job(self) -> Job | None:
        name = self.selected_job_name()
        if not name:
            return None
        return self.db.get_job(name)

    def selected_job_name(self) -> str | None:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        name_item = self.table.item(row, 0)
        if name_item is None:
            return None
        return name_item.text()

    def _job_run_finished(self, job_name: str, exit_code: int, detail: str) -> None:
        self.run_button.setEnabled(True)
        self.refresh()
        if exit_code == 0:
            QMessageBox.information(self, "Sincronização concluída", f"{job_name} finalizado com sucesso.")
        elif exit_code in {-15, 143}:
            QMessageBox.information(self, "Sincronização parada", f"{job_name} foi interrompido.")
        else:
            QMessageBox.warning(self, "Erro na sincronização", f"{job_name} retornou código {exit_code}.\n\n{detail}")

    def _update_buttons(self) -> None:
        job = self.selected_job()
        has_selection = job is not None
        for button in (
            self.edit_button,
            self.remove_button,
            self.pause_button,
            self.resume_button,
            self.run_button,
            self.logs_button,
            self.diagnostics_button,
        ):
            button.setEnabled(has_selection)
        self.stop_button.setEnabled(job is not None and self.locks.is_locked(job))

    def _selection_changed(self) -> None:
        if self._refreshing:
            return
        self._update_buttons()
        self._update_details()

    def _open_job_context_menu(self, position) -> None:
        index = self.table.indexAt(position)
        if index.isValid():
            self.table.selectRow(index.row())
        job = self.selected_job()
        menu = QMenu(self)
        sync_action = menu.addAction("Sincronizar agora")
        stop_action = menu.addAction("Parar")
        menu.addSeparator()
        edit_action = menu.addAction("Editar")
        logs_action = menu.addAction("Ver logs")
        diagnostics_action = menu.addAction("Copiar diagnostico")
        local_action = menu.addAction("Abrir pasta local")
        remote_action = menu.addAction("Navegar remoto")
        command_action = menu.addAction("Copiar comando rclone")
        if job is None:
            for action in menu.actions():
                action.setEnabled(False)
        else:
            stop_action.setEnabled(self.locks.is_locked(job))
        action = menu.exec(self.table.viewport().mapToGlobal(position))
        if action == sync_action:
            self.run_selected_job()
        elif action == stop_action:
            self.stop_job()
        elif action == edit_action:
            self.edit_job()
        elif action == logs_action:
            self.open_logs()
        elif action == diagnostics_action:
            self.copy_diagnostics()
        elif action == local_action:
            self.open_local_folder()
        elif action == remote_action:
            self.browse_selected_remote()
        elif action == command_action:
            self.copy_rclone_command()

    def _update_details(self) -> None:
        job = self.selected_job()
        if job is None:
            self._clear_details()
            return
        status_row = self.db.get_job_status(job.id) if job.id is not None else None
        status = status_row["status"] if status_row else "idle"
        message = status_row["message"] if status_row and status_row["message"] else "-"
        last_run = self.db.get_last_job_run(job.id) if job.id is not None else None
        self.detail_name.setText(job.name)
        self.detail_status.setText(status)
        self.detail_status.setStyleSheet(_status_label_stylesheet(status))
        self.detail_local.setText(job.local_path)
        self.detail_remote.setText(job.remote_path)
        self.detail_mode.setText(job.mode)
        self.detail_direction.setText(_format_direction(job.direction))
        self.detail_realtime.setText("sim" if job.realtime else "não")
        self.detail_run_on_startup.setText("sim" if job.run_on_startup else "não")
        self.detail_schedule.setText(job.schedule_time or "-")
        self.detail_limits.setText(
            f"transfers={job.transfers}, checkers={job.checkers}, bw={job.bandwidth_limit or '-'}"
        )
        self._update_activity_details(job, status, last_run)
        self.detail_updated.setText(status_row["updated_at"] if status_row else job.updated_at or "-")
        self.detail_last_error.setText(message)
        self._populate_history(job)
        self._populate_recent_log(job)

    def _clear_details(self) -> None:
        for label in (
            self.detail_name,
            self.detail_status,
            self.detail_local,
            self.detail_remote,
            self.detail_mode,
            self.detail_direction,
            self.detail_realtime,
            self.detail_run_on_startup,
            self.detail_schedule,
            self.detail_limits,
            self.detail_activity,
            self.detail_progress_text,
            self.detail_log_updated,
            self.detail_updated,
            self.detail_last_error,
        ):
            label.setText("-")
        self.activity_progress.setRange(0, 1)
        self.activity_progress.setValue(0)
        self.detail_status.setStyleSheet("")
        self.history_table.setRowCount(0)
        self.recent_log_text.clear()

    def _populate_history(self, job: Job) -> None:
        runs = self.db.list_job_runs(job.id, limit=25) if job.id is not None else []
        self.history_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            values = [
                run["started_at"] or "-",
                run["finished_at"] or "-",
                run["status"] or "-",
                "-" if run["exit_code"] is None else str(run["exit_code"]),
                "-" if run["duration_seconds"] is None else f"{run['duration_seconds']}s",
                run["log_file"] or "-",
            ]
            status = run["status"] or ""
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                _apply_status_color(item, status)
                self.history_table.setItem(row, column, item)

    def _populate_recent_log(self, job: Job) -> None:
        log_file = ensure_app_dirs().job_log_dir / f"{safe_filename(job.name)}.log"
        if not log_file.exists():
            self.recent_log_text.setPlainText("Sem log ainda.")
            return
        try:
            with log_file.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(size - 120_000, 0))
                text = handle.read().decode("utf-8", errors="replace")
        except OSError as exc:
            self.recent_log_text.setPlainText(f"Não foi possível ler o log: {exc}")
            return
        self.recent_log_text.setPlainText(text)
        self.recent_log_text.verticalScrollBar().setValue(self.recent_log_text.verticalScrollBar().maximum())

    def _update_activity_details(self, job: Job, status: str, last_run) -> None:
        if status in {"running", "pending", "waiting_debounce", "scheduled"}:
            log_file = ensure_app_dirs().job_log_dir / f"{safe_filename(job.name)}.log"
            snapshot = progress_snapshot_from_log(log_file)
            if snapshot.percent is None:
                self.activity_progress.setRange(0, 0)
                self._set_progress_text(_format_progress_snapshot(snapshot))
            else:
                self.activity_progress.setRange(0, 100)
                self.activity_progress.setValue(snapshot.percent)
                self._set_progress_text(_format_progress_snapshot(snapshot))
            if last_run and last_run["started_at"]:
                self.detail_activity.setText(f"Rodando há {_elapsed_since(last_run['started_at'])}")
            else:
                self.detail_activity.setText(_format_status_label(status))
        else:
            self.activity_progress.setRange(0, 100)
            value = 100 if status == "success" else 0
            self.activity_progress.setValue(value)
            self._set_progress_text(f"{value}%" if status == "success" else "-")
            if last_run and last_run["finished_at"]:
                self.detail_activity.setText(f"Última execução: {_elapsed_since(last_run['finished_at'])} atrás")
            else:
                self.detail_activity.setText(_format_status_label(status))

        log_file = ensure_app_dirs().job_log_dir / f"{safe_filename(job.name)}.log"
        if log_file.exists():
            try:
                updated_at = datetime.fromtimestamp(log_file.stat().st_mtime)
            except OSError:
                self.detail_log_updated.setText("-")
                return
            self.detail_log_updated.setText(f"{updated_at.replace(microsecond=0).isoformat()} ({_elapsed_delta(datetime.now() - updated_at)} atrás)")
        else:
            self.detail_log_updated.setText("Sem log ainda")

    def _set_progress_text(self, text: str) -> None:
        display = _ellipsize_middle(text, 180)
        self.detail_progress_text.setText(display)
        self.detail_progress_text.setToolTip(text if text != display else "")

    def _set_auto_refresh(self, enabled: bool) -> None:
        if enabled:
            self.refresh_timer.start()
        else:
            self.refresh_timer.stop()
        self._update_summary(self._all_jobs)

    def _reconcile_runtime_state(self) -> None:
        active_job_ids = [
            job.id
            for job in self.db.list_jobs()
            if job.id is not None and self.locks.is_locked(job)
        ]
        self.db.reconcile_interrupted_jobs(active_job_ids)

    def _job_matches_filters(self, job: Job) -> bool:
        query = self.search_edit.text().strip().lower()
        if query:
            haystack = " ".join([job.name, job.local_path, job.remote_path, job.mode]).lower()
            if query not in haystack:
                return False
        selected_status = self.status_filter_combo.currentText()
        if selected_status == "Todos":
            return True
        status = self.db.get_job_status_text(job.id) if job.id is not None else "idle"
        if not job.enabled:
            status = "paused"
        expected = {
            "Rodando": {"running", "pending", "waiting_debounce", "scheduled"},
            "Erro": {"error"},
            "Pausados": {"paused", "disabled"},
            "Parados": {"stopped"},
            "Sucesso": {"success"},
            "Idle": {"idle"},
        }
        return status in expected.get(selected_status, set())

    def _update_summary(self, jobs: list[Job]) -> None:
        running = 0
        errors = 0
        paused = 0
        for job in jobs:
            status = self.db.get_job_status_text(job.id) if job.id is not None else "idle"
            if not job.enabled:
                status = "paused"
            if status in {"running", "pending", "waiting_debounce", "scheduled"}:
                running += 1
            if status == "error":
                errors += 1
            if status == "paused":
                paused += 1
        auto_refresh = "ativo" if self.auto_refresh_check.isChecked() else "desativado"
        self.summary_label.setText(
            f"Jobs: {len(jobs)} | Rodando: {running} | Erros: {errors} | Pausados: {paused} | Auto-refresh {auto_refresh}"
        )

    def _restore_window_geometry(self) -> None:
        value = self.db.get_setting("main_window_geometry")
        if not value:
            return
        self.restoreGeometry(QByteArray.fromBase64(value.encode("ascii")))

    def _save_window_geometry(self) -> None:
        value = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.db.set_setting("main_window_geometry", value)

    def _diagnostics_text(self, job: Job) -> str:
        rclone_path = self.db.get_setting("rclone_path", "rclone") or "rclone"
        command, log_file = RcloneRunner(db=self.db, rclone_path=rclone_path).build_command(job)
        status_row = self.db.get_job_status(job.id) if job.id is not None else None
        last_run = self.db.get_last_job_run(job.id) if job.id is not None else None
        lines = [
            "Rclone Sync Manager diagnostic",
            f"Generated: {datetime.now().replace(microsecond=0).isoformat()}",
            "",
            f"Job: {job.name}",
            f"Status: {status_row['status'] if status_row else 'idle'}",
            f"Status message: {status_row['message'] if status_row and status_row['message'] else '-'}",
            f"Local path: {job.local_path}",
            f"Remote path: {job.remote_path}",
            f"Mode: {job.mode}",
            f"Direction: {job.direction}",
            f"Realtime: {job.realtime}",
            f"Run on startup: {job.run_on_startup}",
            f"Transfers: {job.transfers}",
            f"Checkers: {job.checkers}",
            f"Bandwidth: {job.bandwidth_limit or '-'}",
            f"Dry run: {job.dry_run}",
            f"Low priority: {job.priority_low}",
            "",
            f"Command: {shell_join(command)}",
            f"Log file: {log_file}",
        ]
        if last_run:
            lines.extend(
                [
                    "",
                    "Last run:",
                    f"  started_at: {last_run['started_at'] or '-'}",
                    f"  finished_at: {last_run['finished_at'] or '-'}",
                    f"  status: {last_run['status'] or '-'}",
                    f"  exit_code: {'-' if last_run['exit_code'] is None else last_run['exit_code']}",
                    f"  duration_seconds: {'-' if last_run['duration_seconds'] is None else last_run['duration_seconds']}",
                    f"  error_message: {last_run['error_message'] or '-'}",
                ]
            )
        tail = _tail_text(log_file, limit=8000)
        if tail:
            lines.extend(["", "Recent log tail:", tail])
        return "\n".join(str(line) for line in lines)


def _format_last_result(row) -> str:
    if row is None:
        return "-"
    status = row["status"] or "-"
    exit_code = row["exit_code"]
    if exit_code is None:
        return status
    return f"{status} ({exit_code})"


def _elapsed_since(value: str) -> str:
    try:
        started = datetime.fromisoformat(value)
    except ValueError:
        return "-"
    return _elapsed_delta(datetime.now() - started)


def _elapsed_delta(delta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _format_progress_snapshot(snapshot) -> str:
    parts = []
    if snapshot.percent is not None:
        parts.append(f"{snapshot.percent}%")
    if snapshot.transferred:
        parts.append(snapshot.transferred)
    if snapshot.speed:
        parts.append(snapshot.speed)
    if snapshot.eta:
        parts.append(f"ETA {snapshot.eta}")
    if snapshot.checks:
        parts.append(f"checks {snapshot.checks}")
    if snapshot.errors and not snapshot.errors.startswith("0 "):
        parts.append(f"erros {snapshot.errors}")
    if snapshot.transferring:
        parts.append("transferindo " + ", ".join(snapshot.transferring[:2]))
    return " | ".join(parts) if parts else "aguardando stats..."


def _ellipsize_middle(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    keep = max(1, (max_length - 3) // 2)
    return f"{value[:keep]}...{value[-keep:]}"


def _local_directory_has_entries(path: str) -> bool:
    try:
        return any(Path(path).iterdir())
    except OSError:
        return False


def _tail_text(path: Path, *, limit: int) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(size - limit, 0))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""




def _format_status_label(status: str) -> str:
    labels = {
        "idle": "IDLE",
        "running": "RODANDO",
        "pending": "PENDENTE",
        "waiting_debounce": "AGUARDANDO",
        "scheduled": "AGENDADO",
        "success": "SUCESSO",
        "error": "ERRO",
        "stopped": "PARADO",
        "paused": "PAUSADO",
        "disabled": "DESATIVADO",
    }
    return labels.get(status, status.upper())


def _status_label_stylesheet(status: str) -> str:
    colors = {
        "running": ("#fff3bf", "#111827"),
        "pending": ("#d0ebff", "#111827"),
        "waiting_debounce": ("#d0ebff", "#111827"),
        "scheduled": ("#d0ebff", "#111827"),
        "success": ("#d3f9d8", "#111827"),
        "error": ("#ffe3e3", "#111827"),
        "stopped": ("#ffe8cc", "#111827"),
        "paused": ("#f1f3f5", "#111827"),
        "idle": ("#e9ecef", "#111827"),
    }
    background, foreground = colors.get(status, ("transparent", "inherit"))
    return (
        f"background-color: {background}; color: {foreground}; "
        "padding: 2px 6px; border-radius: 4px; font-weight: 600;"
    )


def _apply_status_color(item: QTableWidgetItem, status: str) -> None:
    colors = {
        "running": QColor("#fff3bf"),
        "pending": QColor("#d0ebff"),
        "waiting_debounce": QColor("#d0ebff"),
        "success": QColor("#d3f9d8"),
        "error": QColor("#ffe3e3"),
        "stopped": QColor("#ffe8cc"),
        "paused": QColor("#f1f3f5"),
    }
    color = colors.get(status)
    if color:
        item.setBackground(color)
        item.setForeground(QColor("#111827"))


def _format_direction(direction: str) -> str:
    if direction == "remote_to_local":
        return "Remote -> Local"
    return "Local -> Remote"
