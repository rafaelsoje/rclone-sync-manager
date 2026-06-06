from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..rclone_utils import (
    RemoteEntry,
    join_remote_path,
    list_remote_entries_result,
    list_remotes,
    split_remote_path,
)


class RemoteBrowserDialog(QDialog):
    def __init__(self, parent=None, initial_path: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Selecionar remote")
        self.resize(680, 520)
        self.selected_path = initial_path
        self.selected_entries: list[RemoteEntry] = []
        self.current_remote = ""
        self.current_path = ""

        self.remote_combo = QComboBox()
        self.path_label = QLabel("-")
        self.entries_list = QListWidget()
        self.entries_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.up_button = QPushButton("Subir")
        self.refresh_button = QPushButton("Atualizar")

        top = QHBoxLayout()
        top.addWidget(QLabel("Remote"))
        top.addWidget(self.remote_combo)
        top.addWidget(self.up_button)
        top.addWidget(self.refresh_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.path_label)
        layout.addWidget(self.entries_list)
        layout.addWidget(buttons)
        self.setLayout(layout)

        self.remote_combo.currentTextChanged.connect(self._remote_changed)
        self.up_button.clicked.connect(self._go_up)
        self.refresh_button.clicked.connect(self.refresh)
        self.entries_list.itemDoubleClicked.connect(self._open_item)

        self._load_remotes(initial_path)

    def _load_remotes(self, initial_path: str) -> None:
        remotes = list_remotes()
        self.remote_combo.clear()
        self.remote_combo.addItems([f"{remote}:" for remote in remotes])
        initial_remote, initial_subpath = split_remote_path(initial_path)
        if initial_remote:
            index = self.remote_combo.findText(f"{initial_remote}:")
            if index >= 0:
                self.remote_combo.setCurrentIndex(index)
        self.current_remote = self.remote_combo.currentText().rstrip(":")
        self.current_path = initial_subpath
        self.refresh()

    def refresh(self) -> None:
        if not self.current_remote:
            self.entries_list.clear()
            self.path_label.setText("Nenhum remote configurado.")
            return
        current = join_remote_path(self.current_remote, self.current_path)
        self.path_label.setText(current)
        self.selected_path = current
        self.entries_list.clear()
        result = list_remote_entries_result(current)
        if result.error:
            self.path_label.setText(f"{current} — {result.error}")
        elif not result.entries:
            self.path_label.setText(f"{current} — vazio")
        for entry in result.entries:
            item = QListWidgetItem(_entry_label(entry))
            item.setData(Qt.UserRole, entry)
            self.entries_list.addItem(item)

    def _remote_changed(self, remote_text: str) -> None:
        self.current_remote = remote_text.rstrip(":")
        self.current_path = ""
        self.refresh()

    def _go_up(self) -> None:
        if not self.current_path:
            return
        parts = self.current_path.split("/")
        self.current_path = "/".join(parts[:-1])
        self.refresh()

    def _open_item(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.UserRole)
        if not isinstance(entry, RemoteEntry):
            return
        if entry.is_dir:
            _, self.current_path = split_remote_path(entry.path)
            self.refresh()
        else:
            self.selected_path = entry.path
            self.selected_entries = [entry]
            self.accept()

    def _accept_selection(self) -> None:
        self.selected_entries = []
        for item in self.entries_list.selectedItems():
            entry = item.data(Qt.UserRole)
            if isinstance(entry, RemoteEntry):
                self.selected_entries.append(entry)
        if self.selected_entries:
            self.selected_path = self.selected_entries[0].path
        if not self.selected_path:
            QMessageBox.warning(self, "Remote", "Selecione um remote ou pasta.")
            return
        self.accept()


def _entry_label(entry: RemoteEntry) -> str:
    prefix = "[pasta]" if entry.is_dir else "[arquivo]"
    return f"{prefix} {entry.name}"
