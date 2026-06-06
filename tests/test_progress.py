from rclone_sync_manager.progress import progress_from_log, progress_snapshot_from_log


def test_progress_from_log_reads_latest_percentage(tmp_path) -> None:
    log_file = tmp_path / "job.log"
    log_file.write_text(
        """
Transferred:    10 MiB / 100 MiB, 10%, 1 MiB/s, ETA 1m30s
Transferred:    42 MiB / 100 MiB, 42%, 1 MiB/s, ETA 58s
""",
        encoding="utf-8",
    )

    assert progress_from_log(log_file) == 42


def test_progress_snapshot_reads_rclone_stats_block(tmp_path) -> None:
    log_file = tmp_path / "job.log"
    log_file.write_text(
        """
Transferred:      610.534 MiB / 4.394 GiB, 14%, 6.736 MiB/s, ETA 9m37s
Errors:                33 (retrying may help)
Checks:                 0 / 0, -
Transferred:            0 / 3610, 0%
Elapsed time:        49.9s
Transferring:
 *                     www/nexusApp.tar.gz: 42% /190.085 MiB, 3.056 MiB/s, 35s
 *                          shellscript/celular.sh: transferring
""",
        encoding="utf-8",
    )

    snapshot = progress_snapshot_from_log(log_file)

    assert snapshot.percent == 14
    assert snapshot.transferred == "610.534 MiB / 4.394 GiB"
    assert snapshot.speed == "6.736 MiB/s"
    assert snapshot.eta == "9m37s"
    assert snapshot.errors == "33 (retrying may help)"
    assert snapshot.checks == "0 / 0, -"
    assert snapshot.elapsed == "49.9s"
    assert snapshot.transferring == [
        "www/nexusApp.tar.gz: 42% /190.085 MiB, 3.056 MiB/s, 35s",
        "shellscript/celular.sh: transferring",
    ]
