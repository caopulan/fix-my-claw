from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from string import Template

from fix_my_claw.config import AppConfig
from fix_my_claw.openclaw import probe_health, probe_logs, probe_status
from fix_my_claw.proc import CmdResult, run_cmd
from fix_my_claw.state import StateStore
from fix_my_claw.util import ensure_dir, redact_text, truncate_for_log

log = logging.getLogger("fix_my_claw.repair")


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
    results: list[dict] = []
    for idx, step in enumerate(cfg.repair.official_steps, start=1):
        argv = [cfg.openclaw.command if step and step[0] == "openclaw" else step[0], *step[1:]]
        cwd = cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None
        res = run_cmd(argv, timeout_seconds=cfg.repair.step_timeout_seconds, cwd=cwd)
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
            break
    return results


def _render_prompt(template_text: str, vars: dict[str, str]) -> str:
    return Template(template_text).safe_substitute(vars)


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
    prompt = _render_prompt(
        _load_prompt_text(prompt_name),
        {
            "attempt_dir": str(attempt_dir.resolve()),
            "workspace_dir": str(cfg.openclaw.workspace_dir),
            "openclaw_state_dir": str(cfg.openclaw.state_dir),
            "monitor_state_dir": str(cfg.monitor.state_dir),
            "health_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.health_args]),
            "status_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.status_args]),
            "logs_cmd": " ".join([cfg.openclaw.command, *cfg.openclaw.logs_args]),
        },
    )

    argv = _build_ai_cmd(cfg, code_stage=code_stage)
    log.warning("AI repair (%s) starting: %s", "code" if code_stage else "config", argv)
    res = run_cmd(
        argv,
        timeout_seconds=cfg.ai.timeout_seconds,
        cwd=cfg.openclaw.workspace_dir if cfg.openclaw.workspace_dir.exists() else None,
        stdin_text=prompt,
    )
    _write_attempt_file(attempt_dir, "ai.argv.txt", " ".join(argv))
    _write_attempt_file(attempt_dir, "ai.stdout.txt", redact_text(res.stdout))
    _write_attempt_file(attempt_dir, "ai.stderr.txt", redact_text(res.stderr))
    log.warning("AI repair done: exit=%s", res.exit_code)
    if res.stderr:
        log.warning("AI stderr: %s", truncate_for_log(res.stderr))
    return res


def attempt_repair(cfg: AppConfig, store: StateStore, *, force: bool) -> RepairResult:
    healthy_now = _probe_is_healthy(cfg)
    if healthy_now:
        return RepairResult(attempted=False, fixed=True, used_ai=False, details={"already_healthy": True})

    if not cfg.repair.enabled:
        return RepairResult(attempted=False, fixed=False, used_ai=False, details={"repair_disabled": True})

    if not store.can_attempt_repair(cfg.monitor.repair_cooldown_seconds, force=force):
        return RepairResult(attempted=False, fixed=False, used_ai=False, details={"cooldown": True})

    store.mark_repair_attempt()
    attempt_dir = _attempt_dir(cfg)
    details: dict = {"attempt_dir": str(attempt_dir.resolve())}

    details["context_before"] = _collect_context(cfg, attempt_dir)
    details["official"] = _run_official_steps(cfg, attempt_dir)
    details["context_after_official"] = _collect_context(cfg, attempt_dir)

    if _probe_is_healthy(cfg):
        return RepairResult(attempted=True, fixed=True, used_ai=False, details=details)

    used_ai = False
    if cfg.ai.enabled and store.can_attempt_ai(
        max_attempts_per_day=cfg.ai.max_attempts_per_day,
        cooldown_seconds=cfg.ai.cooldown_seconds,
    ):
        store.mark_ai_attempt()
        used_ai = True
        details["ai_config_stage"] = "config"
        details["ai_result_config"] = _run_ai_repair(cfg, attempt_dir, code_stage=False).__dict__
        details["context_after_ai_config"] = _collect_context(cfg, attempt_dir)
        if _probe_is_healthy(cfg):
            return RepairResult(attempted=True, fixed=True, used_ai=True, details=details)

        if cfg.ai.allow_code_changes:
            details["ai_config_stage"] = "code"
            details["ai_result_code"] = _run_ai_repair(cfg, attempt_dir, code_stage=True).__dict__
            details["context_after_ai_code"] = _collect_context(cfg, attempt_dir)

    fixed = _probe_is_healthy(cfg)
    return RepairResult(attempted=True, fixed=fixed, used_ai=used_ai, details=details)
