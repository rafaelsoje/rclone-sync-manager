from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..database import Database
from ..doctor import run_checks


class DoctorDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.db = Database()
        self.setWindowTitle("Doctor")
        self.resize(820, 460)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Status", "Verificação", "Detalhe"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.refresh_button = QPushButton("Atualizar")
        self.close_button = QPushButton("Fechar")
        self.refresh_button.clicked.connect(self.refresh)
        self.close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self.setLayout(layout)
        self.refresh()

    def refresh(self) -> None:
        checks = run_checks(self.db)
        self.table.setRowCount(len(checks))
        for row, check in enumerate(checks):
            values = ["OK" if check.ok else "FAIL", check.name, check.detail]
            color = QColor("#d3f9d8") if check.ok else QColor("#ffe3e3")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setBackground(color)
                item.setForeground(QColor("#111827"))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
