from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from ..autostart import autostart_file_path, is_desktop_autostart_enabled, set_desktop_autostart
from ..config import ensure_app_dirs
from ..database import Database
from ..rclone_utils import delete_remote, list_remotes, open_rclone_config_terminal
from .theme import apply_theme


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.db = Database()
        self.paths = ensure_app_dirs()
        self.setWindowTitle("Configurações")
        self.resize(720, 620)

        self.rclone_path_edit = QLineEdit(self.db.get_setting("rclone_path", "rclone") or "rclone")
        self.max_parallel_spin = QSpinBox()
        self.max_parallel_spin.setRange(1, 16)
        self.max_parallel_spin.setValue(int(self.db.get_setting("max_parallel_jobs", "1") or "1"))
        self.notifications_check = QCheckBox()
        self.notifications_check.setChecked((self.db.get_setting("notifications", "true") or "true") == "true")
        self.autostart_check = QCheckBox()
        self.autostart_check.setChecked(is_desktop_autostart_enabled())
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["system", "light", "dark"])
        self.theme_combo.setCurrentText(self.db.get_setting("theme", "system") or "system")
        self.log_dir_edit = QLineEdit(str(self.paths.log_dir))
        self.state_dir_edit = QLineEdit(str(self.paths.state_dir))
        self.autostart_status = QLineEdit()
        self.autostart_status.setReadOnly(True)
        self.autostart_command = QTextEdit()
        self.autostart_command.setReadOnly(True)
        self.autostart_command.setFixedHeight(90)
        self.recreate_autostart_button = QPushButton("Recriar autostart")
        self.open_autostart_dir_button = QPushButton("Abrir pasta")
        self.open_config_dir_button = QPushButton("Abrir config")
        self.open_data_dir_button = QPushButton("Abrir dados")
        self.open_log_dir_button = QPushButton("Abrir logs")
        self.remotes_table = QTableWidget(0, 1)
        self.remotes_table.setHorizontalHeaderLabels(["Remote"])
        self.remotes_table.horizontalHeader().setStretchLastSection(True)
        self.remotes_table.setMinimumHeight(160)
        self.add_remote_button = QPushButton("Adicionar/editar remote")
        self.remove_remote_button = QPushButton("Remover remote")
        self.refresh_remotes_button = QPushButton("Atualizar remotes")

        form = QFormLayout()
        form.addRow("Caminho do rclone", self.rclone_path_edit)
        form.addRow("Máximo de jobs paralelos", self.max_parallel_spin)
        form.addRow("Notificações desktop", self.notifications_check)
        form.addRow("Iniciar com o sistema", self.autostart_check)
        form.addRow("Tema", self.theme_combo)
        form.addRow("Diretório de logs", self.log_dir_edit)
        form.addRow("Diretório de estado", self.state_dir_edit)
        form.addRow("Autostart", self.autostart_status)
        form.addRow("Arquivo autostart", self.autostart_command)

        autostart_buttons = QHBoxLayout()
        autostart_buttons.addWidget(self.recreate_autostart_button)
        autostart_buttons.addWidget(self.open_autostart_dir_button)
        autostart_buttons.addWidget(self.open_config_dir_button)
        autostart_buttons.addWidget(self.open_data_dir_button)
        autostart_buttons.addWidget(self.open_log_dir_button)
        autostart_buttons.addStretch()

        remotes_buttons = QHBoxLayout()
        remotes_buttons.addWidget(self.add_remote_button)
        remotes_buttons.addWidget(self.remove_remote_button)
        remotes_buttons.addWidget(self.refresh_remotes_button)
        remotes_buttons.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        _clear_button_icons(buttons)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        self.recreate_autostart_button.clicked.connect(self.recreate_autostart)
        self.open_autostart_dir_button.clicked.connect(self.open_autostart_dir)
        self.open_config_dir_button.clicked.connect(lambda: self.open_directory(self.paths.config_dir))
        self.open_data_dir_button.clicked.connect(lambda: self.open_directory(self.paths.data_dir))
        self.open_log_dir_button.clicked.connect(lambda: self.open_directory(self.paths.log_dir))
        self.add_remote_button.clicked.connect(self.open_rclone_config)
        self.remove_remote_button.clicked.connect(self.remove_selected_remote)
        self.refresh_remotes_button.clicked.connect(self.refresh_remotes)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(autostart_buttons)
        layout.addWidget(self.remotes_table)
        layout.addLayout(remotes_buttons)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.refresh_autostart_diagnostics()
        self.refresh_remotes()

    def save(self) -> None:
        previous_autostart = is_desktop_autostart_enabled()
        next_autostart = self.autostart_check.isChecked()
        self.db.set_setting("rclone_path", self.rclone_path_edit.text().strip() or "rclone")
        self.db.set_setting("max_parallel_jobs", str(self.max_parallel_spin.value()))
        self.db.set_setting("notifications", "true" if self.notifications_check.isChecked() else "false")
        self.db.set_setting("theme", self.theme_combo.currentText())
        self.db.set_setting("log_dir", self.log_dir_edit.text().strip())
        self.db.set_setting("state_dir", self.state_dir_edit.text().strip())
        if previous_autostart != next_autostart or is_desktop_autostart_enabled() != next_autostart:
            set_desktop_autostart(next_autostart)
        self.db.set_setting("autostart", "true" if next_autostart else "false")
        apply_theme(self.theme_combo.currentText())
        self.accept()

    def refresh_autostart_diagnostics(self) -> None:
        path = autostart_file_path()
        if path.exists():
            self.autostart_status.setText(f"Ativo: {path}")
            self.autostart_command.setPlainText(path.read_text(encoding="utf-8", errors="replace"))
        else:
            self.autostart_status.setText(f"Inativo: {path}")
            self.autostart_command.setPlainText("Arquivo não existe.")

    def recreate_autostart(self) -> None:
        set_desktop_autostart(True)
        self.autostart_check.setChecked(True)
        self.db.set_setting("autostart", "true")
        self.refresh_autostart_diagnostics()
        QMessageBox.information(self, "Autostart", "Arquivo de autostart recriado.")

    def open_autostart_dir(self) -> None:
        self.open_directory(autostart_file_path().parent)

    def open_directory(self, path) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def refresh_remotes(self) -> None:
        rclone_path = self.rclone_path_edit.text().strip() or "rclone"
        remotes = list_remotes(rclone_path)
        self.remotes_table.setRowCount(len(remotes))
        for row, remote in enumerate(remotes):
            self.remotes_table.setItem(row, 0, QTableWidgetItem(f"{remote}:"))

    def selected_remote(self) -> str | None:
        selected = self.remotes_table.selectedItems()
        if not selected:
            return None
        return selected[0].text().rstrip(":")

    def open_rclone_config(self) -> None:
        rclone_path = self.rclone_path_edit.text().strip() or "rclone"
        ok, message = open_rclone_config_terminal(rclone_path)
        if not ok:
            QMessageBox.warning(self, "rclone config", message)
            return
        QMessageBox.information(
            self,
            "rclone config",
            "O configurador do rclone foi aberto em um terminal. Clique em Atualizar remotes ao terminar.",
        )

    def remove_selected_remote(self) -> None:
        remote = self.selected_remote()
        if not remote:
            QMessageBox.information(self, "Remover remote", "Selecione um remote primeiro.")
            return
        if QMessageBox.warning(
            self,
            "Remover remote",
            f"Remover o remote {remote}: da configuração do rclone?",
            QMessageBox.Cancel | QMessageBox.Yes,
            QMessageBox.Cancel,
        ) != QMessageBox.Yes:
            return
        rclone_path = self.rclone_path_edit.text().strip() or "rclone"
        ok, message = delete_remote(remote, rclone_path)
        if not ok:
            QMessageBox.warning(self, "Remover remote", message or "Não foi possível remover o remote.")
            return
        self.refresh_remotes()
        QMessageBox.information(self, "Remover remote", f"Remote {remote}: removido.")


def _clear_button_icons(buttons: QDialogButtonBox) -> None:
    for button in buttons.buttons():
        button.setIcon(button.icon().__class__())
