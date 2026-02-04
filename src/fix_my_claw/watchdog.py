from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fix_my_claw.config import AppConfig
from fix_my_claw.openclaw import probe_health, probe_status
from fix_my_claw.state import StateStore

log = logging.getLogger("fix_my_claw.watchdog")


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


def monitor_loop(cfg: AppConfig, store: StateStore) -> None:
    from fix_my_claw.repair import attempt_repair

    log.info("starting monitor loop: interval=%ss", cfg.monitor.interval_seconds)
    while True:
        try:
            result = run_check(cfg, store)
            if not result.healthy:
                log.warning("unhealthy; attempting repair")
                attempt_repair(cfg, store, force=False)
        except Exception as e:
            log.exception("monitor loop error: %s", e)
        time.sleep(cfg.monitor.interval_seconds)

