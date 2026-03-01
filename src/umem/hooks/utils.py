from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def cwd_hash(cwd: str) -> str:
    return hashlib.sha256(cwd.encode()).hexdigest()[:16]


def compact_restore_path(cwd: str) -> Path:
    return Path.home() / ".umem" / "compacts" / f"{cwd_hash(cwd)}.json"


def read_stdin_json() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}
