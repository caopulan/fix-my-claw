from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CmdResult:
    argv: list[str]
    cwd: Path | None
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def run_cmd(
    argv: list[str],
    *,
    timeout_seconds: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdin_text: str | None = None,
) -> CmdResult:
    started = time.monotonic()
    try:
        cp = subprocess.run(
            argv,
            input=stdin_text,
            text=True,
            capture_output=True,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            timeout=timeout_seconds,
        )
        code = cp.returncode
        out = cp.stdout or ""
        err = cp.stderr or ""
    except FileNotFoundError as e:
        code = 127
        out = ""
        err = f"[fix-my-claw] command not found: {argv[0]} ({e})"
    except subprocess.TimeoutExpired as e:
        code = 124
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        err = (err + "\n" if err else "") + f"[fix-my-claw] timeout after {timeout_seconds}s"
    except OSError as e:
        code = 1
        out = ""
        err = f"[fix-my-claw] os error running {argv!r}: {e}"
    duration_ms = int((time.monotonic() - started) * 1000)
    return CmdResult(
        argv=list(argv),
        cwd=cwd,
        exit_code=code,
        duration_ms=duration_ms,
        stdout=out,
        stderr=err,
    )
