from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


def _expand_path(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(value))


def _as_path(value: str) -> Path:
    return Path(_expand_path(value)).resolve()


def _get(d: dict[str, Any], key: str, default: Any) -> Any:
    v = d.get(key, default)
    return default if v is None else v


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
    provider: str = "codex"  # "codex" | "claude"
    command: str = "codex"
    # NOTE: args supports placeholders: $workspace_dir, $openclaw_state_dir, $monitor_state_dir
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
    p = Path(_expand_path(path))
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    data = tomllib.loads(p.read_text(encoding="utf-8"))

    monitor = _parse_monitor(dict(data.get("monitor", {})))
    openclaw = _parse_openclaw(dict(data.get("openclaw", {})))
    repair = _parse_repair(dict(data.get("repair", {})))
    ai = _parse_ai(dict(data.get("ai", {})))
    return AppConfig(monitor=monitor, openclaw=openclaw, repair=repair, ai=ai)
