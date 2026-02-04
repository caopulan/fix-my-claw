from __future__ import annotations

import os
import re
from pathlib import Path


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

    # key=value / key: value style
    out = re.sub(
        r'(?i)\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)([^\s"\'`]+)',
        r"\1\2***",
        out,
    )

    # Authorization: Bearer <token>
    out = re.sub(r"(?i)\b(Bearer)\s+([A-Za-z0-9._\\-]+)", r"\1 ***", out)

    for pat in _SECRET_PATTERNS:
        out = re.sub(pat, "sk-***", out)

    return out


def is_executable_on_path(cmd: str) -> bool:
    return any((Path(p) / cmd).exists() for p in os.environ.get("PATH", "").split(os.pathsep))
