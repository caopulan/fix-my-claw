from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileLock:
    path: Path
    _fd: int | None = None

    def acquire(self, *, timeout_seconds: int = 0) -> bool:
        start = time.monotonic()
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, str(os.getpid()).encode("utf-8"))
                self._fd = fd
                return True
            except FileExistsError:
                if self._try_break_stale_lock():
                    continue
                if timeout_seconds <= 0:
                    return False
                if (time.monotonic() - start) >= timeout_seconds:
                    return False
                time.sleep(0.2)

    def _try_break_stale_lock(self) -> bool:
        try:
            pid_text = self.path.read_text(encoding="utf-8").strip()
            pid = int(pid_text) if pid_text else None
        except Exception:
            pid = None

        if pid is None:
            try:
                self.path.unlink(missing_ok=True)
                return True
            except Exception:
                return False

        # Unix: os.kill(pid, 0) checks if process exists.
        try:
            os.kill(pid, 0)
            return False
        except Exception:
            try:
                self.path.unlink(missing_ok=True)
                return True
            except Exception:
                return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass

