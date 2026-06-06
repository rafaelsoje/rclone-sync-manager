from __future__ import annotations

import time

from .config import ensure_app_dirs
from .database import init_default_database
from .lock_manager import LockManager
from .queue_manager import QueueManager
from .remote_watcher import RemotePollerManager
from .scheduler import DailyScheduler
from .startup import enqueue_startup_jobs
from .watcher import WatcherManager


def run_service() -> int:
    db = init_default_database()
    max_parallel = int(db.get_setting("max_parallel_jobs", "1") or "1")
    queue_manager = QueueManager(db=db, max_parallel=max_parallel)
    queue_manager.start()
    watcher = WatcherManager(queue_manager)
    rclone_path = db.get_setting("rclone_path", "rclone") or "rclone"
    remote_watcher = RemotePollerManager(queue_manager, rclone_path=rclone_path)
    watcher.sync_jobs(db.list_jobs())
    remote_watcher.sync_jobs(db.list_jobs())
    locks = LockManager()
    locks.cleanup_stale_locks()
    db.reconcile_interrupted_jobs(
        job.id for job in db.list_jobs() if job.id is not None and locks.is_locked(job)
    )
    scheduler = DailyScheduler(db, queue_manager)
    scheduler.start()
    enqueue_startup_jobs(db, queue_manager)
    print("Rclone Sync Manager service started. Press Ctrl+C to stop.")
    try:
        while True:
            jobs = db.list_jobs()
            watcher.sync_jobs(jobs)
            remote_watcher.sync_jobs(jobs)
            locks.cleanup_stale_locks()
            time.sleep(10)
    except KeyboardInterrupt:
        scheduler.stop()
        watcher.stop_all()
        remote_watcher.stop_all()
        queue_manager.stop()
        return 0


def run_gui(*, start_hidden: bool = False) -> int:
    try:
        from PySide6.QtCore import QLockFile, QTimer
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError as exc:
        raise SystemExit("PySide6 is not installed. Install requirements first.") from exc

    from .gui.main_window import MainWindow
    from .gui.theme import apply_theme
    from .gui.tray import TrayIcon
    from .resources import app_icon_path

    db = init_default_database()
    app = QApplication([])
    icon = QIcon(str(app_icon_path()))
    app.setWindowIcon(icon)
    app.setQuitOnLastWindowClosed(False)
    apply_theme(db.get_setting("theme", "system") or "system")
    instance_lock = QLockFile(str(ensure_app_dirs().state_dir / "gui.lock"))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(100):
        QMessageBox.information(None, "Rclone Sync Manager", "O app já está em execução.")
        return 0
    app.instance_lock = instance_lock

    max_parallel = int(db.get_setting("max_parallel_jobs", "1") or "1")
    queue_manager = QueueManager(db=db, max_parallel=max_parallel)
    queue_manager.start()
    watcher = WatcherManager(queue_manager)
    rclone_path = db.get_setting("rclone_path", "rclone") or "rclone"
    remote_watcher = RemotePollerManager(queue_manager, rclone_path=rclone_path)
    scheduler = DailyScheduler(db, queue_manager)
    scheduler.start()

    def sync_runtime() -> None:
        jobs = db.list_jobs()
        watcher.sync_jobs(jobs)
        remote_watcher.sync_jobs(jobs)

    sync_runtime()
    enqueue_startup_jobs(db, queue_manager)
    runtime_timer = QTimer()
    runtime_timer.setInterval(10_000)
    runtime_timer.timeout.connect(sync_runtime)
    runtime_timer.start()

    def stop_runtime() -> None:
        scheduler.stop()
        watcher.stop_all()
        remote_watcher.stop_all()
        queue_manager.stop()

    app.aboutToQuit.connect(stop_runtime)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.runtime_timer = runtime_timer
    tray = TrayIcon(window)
    tray.show()
    window.tray = tray
    if not start_hidden:
        window.show()
    return app.exec()
