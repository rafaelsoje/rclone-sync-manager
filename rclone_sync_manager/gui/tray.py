from __future__ import annotations

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..resources import app_icon_path


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window) -> None:
        icon = QIcon(str(app_icon_path()))
        super().__init__(icon, window)
        self.window = window
        self.setToolTip("Rclone Sync Manager")

        menu = QMenu()
        open_action = QAction("Abrir Rclone Sync Manager", self)
        pause_all_action = QAction("Pausar todas as sincronizações", self)
        resume_all_action = QAction("Retomar todas as sincronizações", self)
        sync_all_action = QAction("Sincronizar todos agora", self)
        logs_action = QAction("Ver logs", self)
        quit_action = QAction("Sair", self)

        open_action.triggered.connect(self._show_window)
        pause_all_action.triggered.connect(window.pause_all_jobs)
        resume_all_action.triggered.connect(window.resume_all_jobs)
        sync_all_action.triggered.connect(window.run_all_jobs)
        logs_action.triggered.connect(window.open_logs)
        quit_action.triggered.connect(window.quit_app)

        for action in (
            open_action,
            pause_all_action,
            resume_all_action,
            sync_all_action,
            logs_action,
        ):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.setContextMenu(menu)
        self.activated.connect(self._activated)

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
