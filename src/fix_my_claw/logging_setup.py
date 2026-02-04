from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from fix_my_claw.config import AppConfig
from fix_my_claw.util import ensure_dir


def setup_logging(cfg: AppConfig) -> None:
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

