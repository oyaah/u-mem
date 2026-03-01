"""
u-mem SessionStart hook.

Two modes:

1. source == "compact"  — post-compaction restore.
   Reads the pre-compact snapshot and injects structured context (files modified,
   commands run, decisions, last task) so Claude doesn't wake up amnesiac.

2. Normal session start — passive memory injection.
   Injects the 8 most important recent memories for the current project so
   Claude has context from day one, without the user having to say
   "check your memory" or call any tool.

Usage — configured automatically by `u-mem-setup --hooks`:
  ~/.claude/settings.json → hooks.SessionStart hooks
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .utils import compact_restore_path, read_stdin_json


def _inject_recent_memories(cwd: str) -> None:
    """Inject recent project memories into a normal (non-compact) session start."""
    try:
        from umem.config import detect_project, get_db_path
        from umem.database import Database
    except ImportError:
        return

    try:
        project = detect_project(cwd)
        db = Database(get_db_path())
        memories = db.recent(project=project, limit=8)
        db.close()
    except Exception:
        return

    if not memories:
        return

    lines = ["## u-mem: Project Memory", f"*Project: {project}*", ""]
    for m in memories:
        preview = m["content"][:200].strip()
        tags = f" `{'`, `'.join(m['tags'])}`" if m["tags"] else ""
        lines.append(f"- {preview}{tags}")

    output = {"hookSpecificOutput": {"additionalContext": "\n".join(lines)}}
    print(json.dumps(output))


def main() -> None:
    data = read_stdin_json()
    source = str(data.get("source") or "")
    cwd = str(Path(data.get("cwd") or Path.cwd()).resolve())

    if source == "compact":
        # Restore from pre-compact snapshot.
        restore_file = compact_restore_path(cwd)
        try:
            restore_data = json.loads(restore_file.read_text(encoding="utf-8"))
        except Exception:
            sys.exit(0)
        additional_context = str(restore_data.get("additional_context") or "").strip()
        if additional_context:
            print(json.dumps({"hookSpecificOutput": {"additionalContext": additional_context}}))
    else:
        # Normal session start — inject recent memories passively.
        _inject_recent_memories(cwd)

    sys.exit(0)


if __name__ == "__main__":
    main()
