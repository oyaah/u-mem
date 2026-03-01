"""
u-mem SessionStart hook (matcher: compact).

Fires immediately after Claude Code finishes compacting the context window.
Reads the pre-compact snapshot saved by pre_compact.py and injects it back
into Claude's context via the `additionalContext` mechanism.

Without this hook, Claude wakes up post-compact with only a lossy summary of
what it was doing. With this hook, it gets a structured briefing: files touched,
commands run, decisions made, and the last task description.

Usage — configured automatically by `u-mem-setup --hooks`:
  ~/.claude/settings.json  →  hooks.SessionStart[matcher=compact].hooks[0].command = "umem-session-start"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .utils import compact_restore_path, read_stdin_json


def main() -> None:
    data = read_stdin_json()

    # Only act on compact-triggered session starts.
    source = str(data.get("source") or "")
    if source != "compact":
        sys.exit(0)

    cwd = str(data.get("cwd") or Path.cwd())
    restore_file = compact_restore_path(cwd)

    try:
        restore_data = json.loads(restore_file.read_text(encoding="utf-8"))
    except Exception:
        sys.exit(0)

    additional_context = str(restore_data.get("additional_context") or "").strip()
    if not additional_context:
        sys.exit(0)

    # Inject context into the new post-compact session.
    output = {"hookSpecificOutput": {"additionalContext": additional_context}}
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
