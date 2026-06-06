from pathlib import Path

from rclone_sync_manager.config import DEFAULT_IGNORE_PATTERNS
from rclone_sync_manager.utils import path_matches_patterns


def test_default_ignore_patterns_match_common_files() -> None:
    assert path_matches_patterns(Path("/tmp/project/node_modules/pkg/a.js"), DEFAULT_IGNORE_PATTERNS, "/tmp/project")
    assert path_matches_patterns(Path("/tmp/project/file.tmp"), DEFAULT_IGNORE_PATTERNS, "/tmp/project")
    assert path_matches_patterns(Path("/tmp/project/desktop.ini"), DEFAULT_IGNORE_PATTERNS, "/tmp/project")
    assert path_matches_patterns(Path("/tmp/project/~$planilha.xlsx"), DEFAULT_IGNORE_PATTERNS, "/tmp/project")
    assert path_matches_patterns(Path("/tmp/project/.Trash-1000/file.txt"), DEFAULT_IGNORE_PATTERNS, "/tmp/project")
    assert path_matches_patterns(Path("/tmp/project/$RECYCLE.BIN/file.txt"), DEFAULT_IGNORE_PATTERNS, "/tmp/project")
    assert not path_matches_patterns(Path("/tmp/project/src/app.py"), DEFAULT_IGNORE_PATTERNS, "/tmp/project")
