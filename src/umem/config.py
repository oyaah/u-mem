from __future__ import annotations

import os
import subprocess
from pathlib import Path


DB_PATH = Path(os.environ.get("UMEM_DB_PATH", str(Path.home() / ".umem" / "memories.db")))


def get_db_path() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def detect_project(cwd: str | None = None) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
            cwd=cwd or os.getcwd(), timeout=2,
        )
        if r.returncode == 0:
            return Path(r.stdout.strip()).name
    except Exception:
        pass
    return Path(cwd or os.getcwd()).name
