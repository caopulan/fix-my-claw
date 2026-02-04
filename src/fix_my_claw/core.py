from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from string import Template
from typing import Any

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

log = logging.getLogger("fix_my_claw")

DEFAULT_CONFIG_PATH = "~/.fix-my-claw/config.toml"

DEFAULT_CONFIG_TOML = """\
[monitor]
interval_seconds = 60
probe_timeout_seconds = 15
repair_cooldown_seconds = 300
state_dir = "~/.fix-my-claw"
log_file = "~/.fix-my-claw/fix-my-claw.log"
log_level = "INFO"

[openclaw]
command = "openclaw"
state_dir = "~/.openclaw"
workspace_dir = "~/.openclaw/workspace"
health_args = ["gateway", "health", "--json"]
status_args = ["gateway", "status", "--json"]
logs_args = ["logs", "--tail", "200"]

[repair]
enabled = true
official_steps = [
  ["openclaw", "doctor", "--repair"],
  ["openclaw", "gateway", "restart"],
]
step_timeout_seconds = 600
post_step_wait_seconds = 2

[ai]
enabled = false
provider = "codex"
command = "codex"
args = [
  "exec",
  "-s", "workspace-write",
  "-c", "approval_policy=\\"never\\"",
  "--skip-git-repo-check",
  "-C", "$workspace_dir",
  "--add-dir", "$openclaw_state_dir",
  "--add-dir", "$monitor_state_dir",
]
model = "gpt-5.2"
timeout_seconds = 1800
max_attempts_per_day = 2
cooldown_seconds = 3600
allow_code_changes = false
args_code = [
  "exec",
  "-s", "danger-full-access",
  "-c", "approval_policy=\\"never\\"",
  "--skip-git-repo-check",
  "-C", "$workspace_dir",
]
"""


def _expand_path(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(value))


def _as_path(value: str) -> Path:
    return Path(_expand_path(value)).resolve()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def truncate_for_log(s: str, limit: int = 8000) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 20] + f"\n...[truncated {len(s) - limit} chars]"


_SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9]{16,}\b",
]


def redact_text(text: str) -> str:
    out = text
    out = re.sub(
        r'(?i)\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)([^\s"\'`]+)',
        r"\1\2***",
        out,
    )
    out = re.sub(r"(?i)\b(Bearer)\s+([A-Za-z0-9._\\-]+)", r"\1 ***", out)
    for pat in _SECRET_PATTERNS:
        out = re.sub(pat, "sk-***", out)
    return out


def setup_logging(cfg: "AppConfig") -> None:
    ensure_dir(cfg.monitor.state_dir)
    ensure_dir(cfg.monitor.log_file.parent)

    level = getattr(logging, cfg.monitor.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        cfg.monitor.log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(fmt)

    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)


@dataclass(frozen=True)
class MonitorConfig:
    interval_seconds: int = 60
    probe_timeout_seconds: int = 15
    repair_cooldown_seconds: int = 300
    state_dir: Path = field(default_factory=lambda: _as_path("~/.fix-my-claw"))
    log_file: Path = field(default_factory=lambda: _as_path("~/.fix-my-claw/fix-my-claw.log"))
    log_level: str = "INFO"


@dataclass(frozen=True)
class OpenClawConfig:
    command: str = "openclaw"
    state_dir: Path = field(default_factory=lambda: _as_path("~/.openclaw"))
    workspace_dir: Path = field(default_factory=lambda: _as_path("~/.openclaw/workspace"))
    health_args: list[str] = field(default_factory=lambda: ["gateway", "health", "--json"])
    status_args: list[str] = field(default_factory=lambda: ["gateway", "status", "--json"])
    logs_args: list[str] = field(default_factory=lambda: ["logs", "--tail", "200"])


@dataclass(frozen=True)
class RepairConfig:
    enabled: bool = True
    official_steps: list[list[str]] = field(
        default_factory=lambda: [
            ["openclaw", "doctor", "--repair"],
            ["openclaw", "gateway", "restart"],
        ]
    )
    step_timeout_seconds: int = 600
    post_step_wait_seconds: int = 2


@dataclass(frozen=True)
class AiConfig:
    enabled: bool = False
    provider: str = "codex"  # optional/for humans; command+args are what we actually execute
    command: str = "codex"
    # args supports placeholders: $workspace_dir, $openclaw_state_dir, $monitor_state_dir
    args: list[str] = field(
        default_factory=lambda: [
            "exec",
            "-s",
            "workspace-write",
            "-c",
            'approval_policy="never"',
            "--skip-git-repo-check",
            "-C",
            "$workspace_dir",
            "--add-dir",
            "$openclaw_state_dir",
            "--add-dir",
            "$monitor_state_dir",
        ]
    )
    model: str | None = None
    timeout_seconds: int = 1800
    max_attempts_per_day: int = 2
    cooldown_seconds: int = 3600
    allow_code_changes: bool = False
    args_code: list[str] = field(
        default_factory=lambda: [
            "exec",
            "-s",
            "danger-full-access",
            "-c",
            'approval_policy="never"',
            "--skip-git-repo-check",
            "-C",
            "$workspace_dir",
        ]
    )


@dataclass(frozen=True)
class AppConfig:
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)
    repair: RepairConfig = field(default_factory=RepairConfig)
    ai: AiConfig = field(default_factory=AiConfig)


def _get(d: dict[str, Any], key: str, default: Any) -> Any:
    v = d.get(key, default)
    return default if v is None else v


def _parse_monitor(raw: dict[str, Any]) -> MonitorConfig:
    return MonitorConfig(
        interval_seconds=int(_get(raw, "interval_seconds", 60)),
        probe_timeout_seconds=int(_get(raw, "probe_timeout_seconds", 15)),
        repair_cooldown_seconds=int(_get(raw, "repair_cooldown_seconds", 300)),
        state_dir=_as_path(str(_get(raw, "state_dir", "~/.fix-my-claw"))),
        log_file=_as_path(str(_get(raw, "log_file", "~/.fix-my-claw/fix-my-claw.log"))),
        log_level=str(_get(raw, "log_level", "INFO")),
    )


def _parse_openclaw(raw: dict[str, Any]) -> OpenClawConfig:
    return OpenClawConfig(
        command=str(_get(raw, "command", "openclaw")),
        state_dir=_as_path(str(_get(raw, "state_dir", "~/.openclaw"))),
        workspace_dir=_as_path(str(_get(raw, "workspace_dir", "~/.openclaw/workspace"))),
        health_args=list(_get(raw, "health_args", ["gateway", "health", "--json"])),
        status_args=list(_get(raw, "status_args", ["gateway", "status", "--json"])),
        logs_args=list(_get(raw, "logs_args", ["logs", "--tail", "200"])),
    )


def _parse_repair(raw: dict[str, Any]) -> RepairConfig:
    return RepairConfig(
        enabled=bool(_get(raw, "enabled", True)),
        official_steps=[list(x) for x in _get(raw, "official_steps", RepairConfig().official_steps)],
        step_timeout_seconds=int(_get(raw, "step_timeout_seconds", 600)),
        post_step_wait_seconds=int(_get(raw, "post_step_wait_seconds", 2)),
    )


def _parse_ai(raw: dict[str, Any]) -> AiConfig:
    cfg = AiConfig()
    return AiConfig(
        enabled=bool(_get(raw, "enabled", cfg.enabled)),
        provider=str(_get(raw, "provider", cfg.provider)),
        command=str(_get(raw, "command", cfg.command)),
        args=list(_get(raw, "args", cfg.args)),
        model=_get(raw, "model", cfg.model),
        timeout_seconds=int(_get(raw, "timeout_seconds", cfg.timeout_seconds)),
        max_attempts_per_day=int(_get(raw, "max_attempts_per_day", cfg.max_attempts_per_day)),
        cooldown_seconds=int(_get(raw, "cooldown_seconds", cfg.cooldown_seconds)),
        allow_code_changes=bool(_get(raw, "allow_code_changes", cfg.allow_code_changes)),
        args_code=list(_get(raw, "args_code", cfg.args_code)),
    )


def load_config(path: str) -> AppConfig:
    p = _as_path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    monitor = _parse_monitor(dict(data.get("monitor", {})))
    openclaw = _parse_openclaw(dict(data.get("openclaw", {})))
    repair = _parse_repair(dict(data.get("repair", {})))
    ai = _parse_ai(dict(data.get("ai", {})))
    return AppConfig(monitor=monitor, openclaw=openclaw, repair=repair, ai=ai)


def write_default_config(path: str, *, overwrite: bool = False) -> Path:
    p = _as_path(path)
    if p.exists() and not overwrite:
        return p
    ensure_dir(p.parent)
    p.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return p


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


def _now_ts() -> int:
    return int(time.time())


def _today_ymd() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


@dataclass
class State:
    last_ok_ts: int | None = None
    last_repair_ts: int | None = None
    last_ai_ts: int | None = None
    ai_attempts_day: str | None = None
    ai_attempts_count: int = 0

    def to_json(self) -> dict:
        return {
            "last_ok_ts": self.last_ok_ts,
            "last_repair_ts": self.last_repair_ts,
            "last_ai_ts": self.last_ai_ts,
            "ai_attempts_day": self.ai_attempts_day,
            "ai_attempts_count": self.ai_attempts_count,
        }

    @staticmethod
    def from_json(d: dict) -> "State":
        s = State()
        s.last_ok_ts = d.get("last_ok_ts")
        s.last_repair_ts = d.get("last_repair_ts")
        s.last_ai_ts = d.get("last_ai_ts")
        s.ai_attempts_day = d.get("ai_attempts_day")
        s.ai_attempts_count = int(d.get("ai_attempts_count", 0))
        return s


class StateStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.path = base_dir / "state.json"
        ensure_dir(base_dir)

    def load(self) -> State:
        if not self.path.exists():
            return State()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return State.from_json(data if isinstance(data, dict) else {})
        except Exception:
            return State()

    def save(self, state: State) -> None:
        ensure_dir(self.path.parent)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def mark_ok(self) -> None:
        s = self.load()
        s.last_ok_ts = _now_ts()
        self.save(s)

    def can_attempt_repair(self, cooldown_seconds: int, *, force: bool) -> bool:
        if force:
            return True
        s = self.load()
        if s.last_repair_ts is None:
            return True
        return (_now_ts() - s.last_repair_ts) >= cooldown_seconds

    def mark_repair_attempt(self) -> None:
        s = self.load()
        s.last_repair_ts = _now_ts()
        self.save(s)

    def can_attempt_ai(self, *, max_attempts_per_day: int, cooldown_seconds: int) -> bool:
        s = self.load()
        today = _today_ymd()
        if s.ai_attempts_day != today:
            s.ai_attempts_day = today
            s.ai_attempts_count = 0
            self.save(s)

        if s.ai_attempts_count >= max_attempts_per_day:
            return False
        if s.last_ai_ts is not None and (_now_ts() - s.last_ai_ts) < cooldown_seconds:
            return False
        return True

    def mark_ai_attempt(self) -> None:
        s = self.load()
        today = _today_ymd()
        if s.ai_attempts_day != today:
            s.ai_attempts_day = today
            s.ai_attempts_count = 0
        s.ai_attempts_count += 1
        s.last_ai_ts = _now_ts()
        self.save(s)


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
        logging.getLogger("fix_my_claw.openclaw").warning(
            "health probe failed: %s", truncate_for_log(cmd.stderr or cmd.stdout)
        )
    return Probe(name="health", cmd=cmd, json_data=data)


def probe_status(cfg: AppConfig, *, log_on_fail: bool = True) -> Probe:
    argv = [cfg.openclaw.command, *cfg.openclaw.status_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    cmd = run_cmd(argv, timeout_seconds=cfg.monitor.probe_timeout_seconds, cwd=cwd)
    data = _parse_json_maybe(cmd.stdout)
    if log_on_fail and not cmd.ok:
        logging.getLogger("fix_my_claw.openclaw").warning(
            "status probe failed: %s", truncate_for_log(cmd.stderr or cmd.stdout)
        )
    return Probe(name="status", cmd=cmd, json_data=data)


def probe_logs(cfg: AppConfig, *, timeout_seconds: int = 15) -> CmdResult:
    argv = [cfg.openclaw.command, *cfg.openclaw.logs_args]
    cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
    return run_cmd(argv, timeout_seconds=timeout_seconds, cwd=cwd)


@dataclass(frozen=True)
class CheckResult:
    healthy: bool
    health: dict
    status: dict

    def to_json(self) -> dict:
        return {"healthy": self.healthy, "health": self.health, "status": self.status}


def run_check(cfg: AppConfig, store: StateStore) -> CheckResult:
    h = probe_health(cfg)
    s = probe_status(cfg)
    healthy = h.ok and s.ok
    if healthy:
        store.mark_ok()
    return CheckResult(healthy=healthy, health=h.to_json(), status=s.to_json())


@dataclass(frozen=True)
class RepairResult:
    attempted: bool
    fixed: bool
    used_ai: bool
    details: dict

    def to_json(self) -> dict:
        return {
            "attempted": self.attempted,
            "fixed": self.fixed,
            "used_ai": self.used_ai,
            "details": self.details,
        }


def _attempt_dir(cfg: AppConfig) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    d = cfg.monitor.state_dir / "attempts" / ts
    ensure_dir(d)
    return d


def _write_attempt_file(dir_: Path, name: str, content: str) -> Path:
    p = dir_ / name
    p.write_text(content, encoding="utf-8")
    return p


def _collect_context(cfg: AppConfig, attempt_dir: Path) -> dict:
    health = probe_health(cfg, log_on_fail=False)
    status = probe_status(cfg, log_on_fail=False)
    logs = probe_logs(cfg, timeout_seconds=cfg.monitor.probe_timeout_seconds)

    _write_attempt_file(attempt_dir, "health.stdout.txt", redact_text(health.cmd.stdout))
    _write_attempt_file(attempt_dir, "health.stderr.txt", redact_text(health.cmd.stderr))
    _write_attempt_file(attempt_dir, "status.stdout.txt", redact_text(status.cmd.stdout))
    _write_attempt_file(attempt_dir, "status.stderr.txt", redact_text(status.cmd.stderr))
    _write_attempt_file(attempt_dir, "openclaw.logs.txt", redact_text(logs.stdout + ("\n" + logs.stderr if logs.stderr else "")))

    return {
        "health": health.to_json(),
        "status": status.to_json(),
        "logs": {
            "ok": logs.ok,
            "exit_code": logs.exit_code,
            "duration_ms": logs.duration_ms,
            "argv": logs.argv,
            "stdout_path": str((attempt_dir / "openclaw.logs.txt").resolve()),
        },
        "attempt_dir": str(attempt_dir.resolve()),
    }


def _probe_is_healthy(cfg: AppConfig) -> bool:
    return probe_health(cfg, log_on_fail=False).ok and probe_status(cfg, log_on_fail=False).ok


def _run_official_steps(cfg: AppConfig, attempt_dir: Path) -> list[dict]:
    repair_log = logging.getLogger("fix_my_claw.repair")
    results: list[dict] = []
    total = len(cfg.repair.official_steps)
    for idx, step in enumerate(cfg.repair.official_steps, start=1):
        argv = [cfg.openclaw.command if step and step[0] == "openclaw" else step[0], *step[1:]]
        repair_log.warning("official step %d/%d: %s", idx, total, " ".join(argv))
        cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
        res = run_cmd(argv, timeout_seconds=cfg.repair.step_timeout_seconds, cwd=cwd)
        repair_log.warning(
            "official step %d/%d done: exit=%s duration_ms=%s",
            idx,
            total,
            res.exit_code,
            res.duration_ms,
        )
        if res.stderr:
            repair_log.info("official step %d/%d stderr: %s", idx, total, truncate_for_log(res.stderr))
        _write_attempt_file(attempt_dir, f"official.{idx}.stdout.txt", redact_text(res.stdout))
        _write_attempt_file(attempt_dir, f"official.{idx}.stderr.txt", redact_text(res.stderr))
        results.append(
            {
                "argv": res.argv,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "stdout_path": str((attempt_dir / f"official.{idx}.stdout.txt").resolve()),
                "stderr_path": str((attempt_dir / f"official.{idx}.stderr.txt").resolve()),
            }
        )
        time.sleep(cfg.repair.post_step_wait_seconds)
        if _probe_is_healthy(cfg):
            repair_log.warning("OpenClaw is healthy after official step %d/%d", idx, total)
            break
    return results


def _load_prompt_text(name: str) -> str:
    from importlib.resources import files

    return (files("fix_my_claw.prompts") / name).read_text(encoding="utf-8")


def _build_ai_cmd(cfg: AppConfig, *, code_stage: bool) -> list[str]:
    vars = {
        "workspace_dir": str(cfg.openclaw.workspace_dir),
        "openclaw_state_dir": str(cfg.openclaw.state_dir),
        "monitor_state_dir": str(cfg.monitor.state_dir),
    }
    args = cfg.ai.args_code if code_stage else cfg.ai.args
    rendered = [Template(x).safe_substitute(vars) for x in args]
    argv = [cfg.ai.command]
    if cfg.ai.model:
        argv += ["-m", cfg.ai.model]
    argv += rendered
    return argv


def _run_ai_repair(cfg: AppConfig, attempt_dir: Path, *, code_stage: bool) -> CmdResult:
    prompt_name = "repair_code.md" if code_stage else "repair.md"
    prompt = Template(_load_prompt_text(prompt_name)).safe_substitute(
        {
            "attempt_dir": str(attempt_dir.resolve()),
            "workspace_dir": str(cfg.openclaw.workspace_dir),
            "openclaw_state_dir": str(cfg.openclaw.state_dir),
            "monitor_state_dir": str(cfg.monitor.state_dir),
            "health_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.health_args]),
            "status_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.status_args]),
            "logs_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.logs_args]),
        }
    )

    argv = _build_ai_cmd(cfg, code_stage=code_stage)
    logging.getLogger("fix_my_claw.repair").warning(
        "AI repair (%s) starting: %s", "code" if code_stage else "config", argv
    )
    res = run_cmd(
        argv,
        timeout_seconds=cfg.ai.timeout_seconds,
        cwd=cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None,
        stdin_text=prompt,
    )
    _write_attempt_file(attempt_dir, "ai.argv.txt", " ".join(argv))
    _write_attempt_file(attempt_dir, "ai.stdout.txt", redact_text(res.stdout))
    _write_attempt_file(attempt_dir, "ai.stderr.txt", redact_text(res.stderr))
    logging.getLogger("fix_my_claw.repair").warning("AI repair done: exit=%s", res.exit_code)
    if res.stderr:
        logging.getLogger("fix_my_claw.repair").warning("AI stderr: %s", truncate_for_log(res.stderr))
    return res


def attempt_repair(cfg: AppConfig, store: StateStore, *, force: bool) -> RepairResult:
    repair_log = logging.getLogger("fix_my_claw.repair")
    if _probe_is_healthy(cfg):
        repair_log.info("repair skipped: already healthy")
        return RepairResult(attempted=False, fixed=True, used_ai=False, details={"already_healthy": True})

    if not cfg.repair.enabled:
        repair_log.warning("repair skipped: disabled by config")
        return RepairResult(attempted=False, fixed=False, used_ai=False, details={"repair_disabled": True})

    if not store.can_attempt_repair(cfg.monitor.repair_cooldown_seconds, force=force):
        details: dict[str, object] = {"cooldown": True}
        state = store.load()
        if state.last_repair_ts is not None:
            elapsed = _now_ts() - state.last_repair_ts
            remaining = max(0, cfg.monitor.repair_cooldown_seconds - elapsed)
            details["cooldown_remaining_seconds"] = remaining
            repair_log.info("repair skipped: cooldown (%ss remaining)", remaining)
        else:
            repair_log.info("repair skipped: cooldown")
        return RepairResult(attempted=False, fixed=False, used_ai=False, details=details)

    store.mark_repair_attempt()
    attempt_dir = _attempt_dir(cfg)
    details: dict = {"attempt_dir": str(attempt_dir.resolve())}
    repair_log.warning("starting repair attempt: dir=%s", attempt_dir.resolve())

    details["context_before"] = _collect_context(cfg, attempt_dir)
    details["official"] = _run_official_steps(cfg, attempt_dir)
    details["context_after_official"] = _collect_context(cfg, attempt_dir)

    if _probe_is_healthy(cfg):
        repair_log.warning("recovered by official steps: dir=%s", attempt_dir.resolve())
        return RepairResult(attempted=True, fixed=True, used_ai=False, details=details)

    used_ai = False
    if not cfg.ai.enabled:
        repair_log.info("Codex-assisted remediation disabled; leaving OpenClaw unhealthy")
    elif not store.can_attempt_ai(
        max_attempts_per_day=cfg.ai.max_attempts_per_day,
        cooldown_seconds=cfg.ai.cooldown_seconds,
    ):
        repair_log.warning("Codex-assisted remediation skipped (rate limit / cooldown)")
    else:
        store.mark_ai_attempt()
        used_ai = True
        details["ai_stage"] = "config"
        details["ai_result_config"] = _run_ai_repair(cfg, attempt_dir, code_stage=False).__dict__
        details["context_after_ai_config"] = _collect_context(cfg, attempt_dir)
        if _probe_is_healthy(cfg):
            repair_log.warning("recovered by Codex-assisted remediation: dir=%s", attempt_dir.resolve())
            return RepairResult(attempted=True, fixed=True, used_ai=True, details=details)

        if cfg.ai.allow_code_changes:
            details["ai_stage"] = "code"
            details["ai_result_code"] = _run_ai_repair(cfg, attempt_dir, code_stage=True).__dict__
            details["context_after_ai_code"] = _collect_context(cfg, attempt_dir)

    fixed = _probe_is_healthy(cfg)
    repair_log.warning(
        "repair attempt finished: fixed=%s used_codex=%s dir=%s",
        fixed,
        used_ai,
        attempt_dir.resolve(),
    )
    return RepairResult(attempted=True, fixed=fixed, used_ai=used_ai, details=details)


def monitor_loop(cfg: AppConfig, store: StateStore) -> None:
    wd_log = logging.getLogger("fix_my_claw.watchdog")
    wd_log.info("starting monitor loop: interval=%ss", cfg.monitor.interval_seconds)
    while True:
        try:
            result = run_check(cfg, store)
            if not result.healthy:
                wd_log.warning(
                    "unhealthy: health_exit=%s status_exit=%s; attempting repair",
                    result.health.get("exit_code"),
                    result.status.get("exit_code"),
                )
                rr = attempt_repair(cfg, store, force=False)
                if rr.attempted:
                    wd_log.warning(
                        "repair finished: fixed=%s used_codex=%s dir=%s",
                        rr.fixed,
                        rr.used_ai,
                        rr.details.get("attempt_dir"),
                    )
                elif rr.details.get("cooldown"):
                    remaining = rr.details.get("cooldown_remaining_seconds")
                    wd_log.info("repair skipped: cooldown (%ss remaining)", remaining if remaining is not None else "?")
                else:
                    wd_log.info("repair skipped: %s", rr.details)
        except Exception as e:
            wd_log.exception("monitor loop error: %s", e)
        time.sleep(cfg.monitor.interval_seconds)


def _default_config_path() -> str:
    return DEFAULT_CONFIG_PATH


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=_default_config_path(),
        help=f"Path to TOML config file (default: {DEFAULT_CONFIG_PATH}).",
    )


def _load_or_init_config(path: str, *, init_if_missing: bool) -> AppConfig:
    p = _as_path(path)
    if not p.exists():
        if init_if_missing:
            write_default_config(str(p), overwrite=False)
        else:
            raise FileNotFoundError(f"config not found: {p} (run `fix-my-claw init` or `fix-my-claw up`)")
    return load_config(str(p))


def cmd_init(args: argparse.Namespace) -> int:
    p = write_default_config(args.config, overwrite=args.force)
    print(str(p))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    result = run_check(cfg, store)
    if args.json:
        print(json.dumps(result.to_json(), ensure_ascii=False))
    return 0 if result.healthy else 1


def cmd_repair(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)
    lock = FileLock(cfg.monitor.state_dir / "fix-my-claw.lock")
    if not lock.acquire(timeout_seconds=0):
        print("another fix-my-claw instance is running", file=sys.stderr)
        return 2
    store = StateStore(cfg.monitor.state_dir)
    try:
        result = attempt_repair(cfg, store, force=args.force)
    finally:
        lock.release()
    if args.json:
        print(json.dumps(result.to_json(), ensure_ascii=False))
    return 0 if result.fixed else 1


def cmd_monitor(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=False)
    setup_logging(cfg)
    lock = FileLock(cfg.monitor.state_dir / "fix-my-claw.lock")
    if not lock.acquire(timeout_seconds=0):
        print("another fix-my-claw instance is running", file=sys.stderr)
        return 2
    store = StateStore(cfg.monitor.state_dir)
    try:
        monitor_loop(cfg, store)
    finally:
        lock.release()
    return 0


def cmd_up(args: argparse.Namespace) -> int:
    cfg = _load_or_init_config(args.config, init_if_missing=True)
    setup_logging(cfg)
    lock = FileLock(cfg.monitor.state_dir / "fix-my-claw.lock")
    if not lock.acquire(timeout_seconds=0):
        print("another fix-my-claw instance is running", file=sys.stderr)
        return 2
    store = StateStore(cfg.monitor.state_dir)
    try:
        monitor_loop(cfg, store)
    finally:
        lock.release()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fix-my-claw")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_up = sub.add_parser("up", help="One-command start: init default config (if missing) then monitor.")
    _add_config_arg(p_up)
    p_up.set_defaults(func=cmd_up)

    p_init = sub.add_parser("init", help="Write default config (prints config path).")
    _add_config_arg(p_init)
    p_init.add_argument("--force", action="store_true", help="Overwrite config if it already exists.")
    p_init.set_defaults(func=cmd_init)

    p_check = sub.add_parser("check", help="Probe OpenClaw health/status once.")
    _add_config_arg(p_check)
    p_check.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p_check.set_defaults(func=cmd_check)

    p_repair = sub.add_parser("repair", help="Run official repair (and optional AI repair) once if unhealthy.")
    _add_config_arg(p_repair)
    p_repair.add_argument("--force", action="store_true", help="Ignore cooldown and attempt repair.")
    p_repair.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p_repair.set_defaults(func=cmd_repair)

    p_mon = sub.add_parser("monitor", help="Run 24/7 monitor loop (requires config to exist).")
    _add_config_arg(p_mon)
    p_mon.set_defaults(func=cmd_monitor)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)
