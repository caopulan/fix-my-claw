from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from fix_my_claw.config import AppConfig
from fix_my_claw.proc import CmdResult, run_cmd
from fix_my_claw.util import truncate_for_log

log = logging.getLogger("fix_my_claw.openclaw")


@dataclass(frozen=True)
class Probe:
    name: str
    cmd: CmdResult
    json_data: dict | list | None

    @property
    def ok(self) -> bool:
        return self.cmd.ok

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "exit_code": self.cmd.exit_code,
            "duration_ms": self.cmd.duration_ms,
            "argv": self.cmd.argv,
            "stdout": self.cmd.stdout,
            "stderr": self.cmd.stderr,
            "json": self.json_data,
        }


def _parse_json_maybe(stdout: str) -> dict | list | None:
    s = stdout.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def probe_health(cfg: AppConfig, *, log_on_fail: bool = True) -> Probe:
    argv = [cfg.openclaw.command, *cfg.openclaw.health_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    cmd = run_cmd(argv, timeout_seconds=cfg.monitor.probe_timeout_seconds, cwd=cwd)
    data = _parse_json_maybe(cmd.stdout)
    if log_on_fail and not cmd.ok:
        log.warning("health probe failed: %s", truncate_for_log(cmd.stderr or cmd.stdout))
    return Probe(name="health", cmd=cmd, json_data=data)


def probe_status(cfg: AppConfig, *, log_on_fail: bool = True) -> Probe:
    argv = [cfg.openclaw.command, *cfg.openclaw.status_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    cmd = run_cmd(argv, timeout_seconds=cfg.monitor.probe_timeout_seconds, cwd=cwd)
    data = _parse_json_maybe(cmd.stdout)
    if log_on_fail and not cmd.ok:
        log.warning("status probe failed: %s", truncate_for_log(cmd.stderr or cmd.stdout))
    return Probe(name="status", cmd=cmd, json_data=data)


def probe_logs(cfg: AppConfig, *, timeout_seconds: int = 15) -> CmdResult:
    argv = [cfg.openclaw.command, *cfg.openclaw.logs_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    return run_cmd(argv, timeout_seconds=timeout_seconds, cwd=cwd)
