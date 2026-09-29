from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..config import ensure_app_dirs
from ..progress import progress_snapshot_from_log
from ..resources import app_icon_path
from ..utils import safe_filename


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window

        self._generate_icons()
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(120)
        self._anim_timer.timeout.connect(self._step_sync_animation)
        self._anim_frame = 0
        self._is_syncing = False

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(2000)
        self._status_timer.timeout.connect(self.update_status)
        self._status_timer.start()

        self.setIcon(self._icon_idle)
        self.setToolTip("Rclone Sync Manager - Tudo atualizado")

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._build_menu)
        self.setContextMenu(self.menu)
        self._build_menu()

        self.activated.connect(self._activated)

    def _generate_icons(self) -> None:
        path = str(app_icon_path())
        raw_icon = QIcon(path)
        base_pix = raw_icon.pixmap(64, 64)
        if base_pix.isNull():
            base_pix = QPixmap(64, 64)
            base_pix.fill(Qt.transparent)
            p = QPainter(base_pix)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor("#2563eb"))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(6, 6, 52, 52, 12, 12)
            p.end()

        # 1. Ícone Idle (com badge verde de checkmark)
        idle_pix = QPixmap(base_pix)
        p = QPainter(idle_pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#10b981"))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(38, 38, 24, 24)
        pen = QPen(QColor("#ffffff"), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(44, 50, 48, 54)
        p.drawLine(48, 54, 56, 44)
        p.end()
        self._icon_idle = QIcon(idle_pix)

        # 2. Ícone de Erro (com badge vermelho de exclamação)
        err_pix = QPixmap(base_pix)
        p = QPainter(err_pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#ef4444"))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(38, 38, 24, 24)
        pen = QPen(QColor("#ffffff"), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(50, 43, 50, 51)
        p.drawPoint(50, 55)
        p.end()
        self._icon_error = QIcon(err_pix)

        # 3. Ícone de Pausado (com badge âmbar)
        paused_pix = QPixmap(base_pix)
        p = QPainter(paused_pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#f59e0b"))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(38, 38, 24, 24)
        pen = QPen(QColor("#ffffff"), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(47, 44, 47, 54)
        p.drawLine(53, 44, 53, 54)
        p.end()
        self._icon_paused = QIcon(paused_pix)

        # 4. Frames animados de sincronização (rotação suave dos arcos)
        self._sync_frames: list[QIcon] = []
        for angle in range(0, 360, 30):
            pix = QPixmap(base_pix)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor("#0284c7"))
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawEllipse(38, 38, 24, 24)
            p.save()
            p.translate(50, 50)
            p.rotate(angle)
            pen = QPen(QColor("#ffffff"), 2.5)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawArc(-7, -7, 14, 14, 45 * 16, 180 * 16)
            p.drawArc(-7, -7, 14, 14, 225 * 16, 180 * 16)
            p.restore()
            p.end()
            self._sync_frames.append(QIcon(pix))

    def _step_sync_animation(self) -> None:
        if not self._sync_frames:
            return
        self._anim_frame = (self._anim_frame + 1) % len(self._sync_frames)
        self.setIcon(self._sync_frames[self._anim_frame])

    def _get_active_sync_info(self) -> dict:
        db = self.window.db
        locks = self.window.locks
        paths = getattr(self.window, "paths", None) or ensure_app_dirs()
        jobs = db.list_jobs()

        running_jobs = []
        has_errors = False
        last_error_job = None
        last_finished_at = None
        enabled_count = 0

        for job in jobs:
            if job.enabled:
                enabled_count += 1
            status_text = db.get_job_status_text(job.id) if job.id else "idle"
            is_active = (job.id and locks.is_locked(job)) or status_text in ("running", "waiting_debounce")
            if is_active:
                log_file = paths.job_log_dir / f"{safe_filename(job.name)}.log"
                snapshot = progress_snapshot_from_log(log_file)
                running_jobs.append((job, snapshot))
            elif status_text == "error":
                has_errors = True
                if not last_error_job:
                    last_error_job = job

            last_run = db.get_last_job_run(job.id) if job.id else None
            if last_run and last_run.get("finished_at"):
                t = last_run["finished_at"]
                if not last_finished_at or t > last_finished_at:
                    last_finished_at = t

        return {
            "running_jobs": running_jobs,
            "has_errors": has_errors,
            "last_error_job": last_error_job,
            "last_finished_at": last_finished_at,
            "is_all_paused": enabled_count == 0,
        }

    def _build_menu(self) -> None:
        self.menu.clear()
        info = self._get_active_sync_info()
        running_jobs = info["running_jobs"]

        if running_jobs:
            for job, snapshot in running_jobs:
                header = self.menu.addAction(f"🔄 Sincronizando: {job.name}")
                font = header.font()
                font.setBold(True)
                header.setFont(font)
                header.setEnabled(False)

                if snapshot.percent is not None or snapshot.speed:
                    progress_parts = []
                    if snapshot.percent is not None:
                        progress_parts.append(f"{snapshot.percent}%")
                    if snapshot.speed:
                        progress_parts.append(snapshot.speed)
                    if snapshot.eta:
                        progress_parts.append(f"ETA: {snapshot.eta}")
                    prog_action = self.menu.addAction(f"   📊 {' • '.join(progress_parts)}")
                    prog_action.setEnabled(False)

                if snapshot.transferring:
                    for entry in snapshot.transferring[:5]:
                        parts = entry.split(":", 1)
                        filename = Path(parts[0].strip()).name
                        status_note = parts[1].strip() if len(parts) > 1 else "transferindo"
                        file_action = self.menu.addAction(f"   📄 {filename} ({status_note})")
                        file_action.setEnabled(False)
                elif snapshot.transferred:
                    trans_action = self.menu.addAction(f"   Transferido: {snapshot.transferred}")
                    trans_action.setEnabled(False)

        elif info["is_all_paused"]:
            status_action = self.menu.addAction("⏸ Sincronizações pausadas")
            font = status_action.font()
            font.setBold(True)
            status_action.setFont(font)
            status_action.setEnabled(False)
        elif info["has_errors"]:
            err_name = info["last_error_job"].name if info["last_error_job"] else "Job"
            status_action = self.menu.addAction(f"⚠️ Atenção: erro em {err_name}")
            font = status_action.font()
            font.setBold(True)
            status_action.setFont(font)
            status_action.setEnabled(False)
        else:
            status_action = self.menu.addAction("✔ Tudo sincronizado e atualizado")
            font = status_action.font()
            font.setBold(True)
            status_action.setFont(font)
            status_action.setEnabled(False)
            if info["last_finished_at"]:
                last_time = info["last_finished_at"].replace("T", " ")[:19]
                sub = self.menu.addAction(f"   Última sincronização: {last_time}")
                sub.setEnabled(False)

        self.menu.addSeparator()

        open_action = QAction("Abrir Rclone Sync Manager", self)
        open_action.triggered.connect(self._show_window)
        self.menu.addAction(open_action)

        if info["is_all_paused"]:
            resume_action = QAction("Retomar todas as sincronizações", self)
            resume_action.triggered.connect(self.window.resume_all_jobs)
            self.menu.addAction(resume_action)
        else:
            pause_action = QAction("Pausar todas as sincronizações", self)
            pause_action.triggered.connect(self.window.pause_all_jobs)
            self.menu.addAction(pause_action)

        sync_all_action = QAction("Sincronizar todos agora", self)
        sync_all_action.triggered.connect(self.window.run_all_jobs)
        self.menu.addAction(sync_all_action)

        logs_action = QAction("Ver logs", self)
        logs_action.triggered.connect(self.window.open_logs)
        self.menu.addAction(logs_action)

        self.menu.addSeparator()
        quit_action = QAction("Sair", self)
        quit_action.triggered.connect(self.window.quit_app)
        self.menu.addAction(quit_action)

    def update_status(self) -> None:
        info = self._get_active_sync_info()
        running_jobs = info["running_jobs"]

        if running_jobs:
            if not self._is_syncing:
                self._is_syncing = True
                self._anim_timer.start()
            job_names = ", ".join(j.name for j, _ in running_jobs)
            first_snapshot = running_jobs[0][1]
            speed_str = f" • {first_snapshot.speed}" if first_snapshot.speed else ""
            pct_str = f" ({first_snapshot.percent}%)" if first_snapshot.percent is not None else ""
            self.setToolTip(f"Rclone Sync Manager\nSincronizando: {job_names}{pct_str}{speed_str}")
        else:
            if self._is_syncing:
                self._is_syncing = False
                self._anim_timer.stop()

            if info["is_all_paused"]:
                self.setIcon(self._icon_paused)
                self.setToolTip("Rclone Sync Manager - Pausado")
            elif info["has_errors"]:
                self.setIcon(self._icon_error)
                err_name = info["last_error_job"].name if info["last_error_job"] else ""
                self.setToolTip(f"Rclone Sync Manager - Erro em {err_name}")
            else:
                self.setIcon(self._icon_idle)
                self.setToolTip("Rclone Sync Manager - Tudo atualizado")

    def show_desktop_notification(self, title: str, message: str, is_error: bool = False) -> None:
        icon = QSystemTrayIcon.Critical if is_error else QSystemTrayIcon.Information
        self.showMessage(title, message, icon, 4000)

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
