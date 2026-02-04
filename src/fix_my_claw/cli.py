from __future__ import annotations

import argparse
import json
import sys

from fix_my_claw.config import load_config
from fix_my_claw.lock import FileLock
from fix_my_claw.logging_setup import setup_logging
from fix_my_claw.repair import attempt_repair
from fix_my_claw.state import StateStore
from fix_my_claw.watchdog import monitor_loop, run_check


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        required=True,
        help="Path to TOML config file (see examples/fix-my-claw.toml).",
    )


def cmd_check(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    setup_logging(cfg)
    store = StateStore(cfg.monitor.state_dir)
    result = run_check(cfg, store)
    if args.json:
        print(json.dumps(result.to_json(), ensure_ascii=False))
    return 0 if result.healthy else 1


def cmd_repair(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
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
    cfg = load_config(args.config)
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

    p_check = sub.add_parser("check", help="Probe OpenClaw health/status once.")
    _add_common(p_check)
    p_check.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p_check.set_defaults(func=cmd_check)

    p_repair = sub.add_parser(
        "repair",
        help="Run official repair (and optional AI repair) once if unhealthy.",
    )
    _add_common(p_repair)
    p_repair.add_argument("--force", action="store_true", help="Ignore cooldown and attempt repair.")
    p_repair.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    p_repair.set_defaults(func=cmd_repair)

    p_mon = sub.add_parser("monitor", help="Run 24/7 monitor loop.")
    _add_common(p_mon)
    p_mon.set_defaults(func=cmd_monitor)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)
