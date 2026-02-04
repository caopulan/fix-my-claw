from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from fix_my_claw.util import ensure_dir


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

