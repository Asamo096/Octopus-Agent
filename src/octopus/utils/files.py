"""File utilities — atomic writes, file locking."""

from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write(path: Path | str, content: str | bytes) -> None:
    """Write to a file atomically using temp file + rename.

    This prevents partial writes if the process is interrupted.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file in the same directory
    mode = "wb" if isinstance(content, bytes) else "w"
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, mode) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class file_lock:
    """Context manager for exclusive file locking.

    Usage:
        with file_lock("/tmp/my.lock"):
            # Exclusive access
            do_work()
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._fd: int | None = None

    def __enter__(self) -> file_lock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self._path), os.O_CREAT | os.O_WRONLY)
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
