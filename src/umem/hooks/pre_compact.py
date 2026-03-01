"""
u-mem PreCompact hook.

Fires before Claude Code auto-compacts the context window. Reads the
transcript JSONL, extracts what was being worked on, and saves a structured
checkpoint to u-mem so it survives the compaction boundary.

The paired SessionStart hook (session_start.py) reads this snapshot and
injects it back into Claude's context via additionalContext.

Usage — configured automatically by `u-mem-setup --hooks`:
  ~/.claude/settings.json  →  hooks.PreCompact[0].hooks[0].command = "umem-pre-compact"
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .utils import compact_restore_path, read_stdin_json


# Keywords that flag a sentence as a decision or finding worth saving.
_DECISION_KW = frozenset({
    "decided", "decision", "because", "chose", "choice", "approach",
    "instead", "rather than", "switched", "using", "implemented",
    "fixed", "fix", "resolved", "workaround", "patch",
    "bug", "error", "issue", "problem", "exception", "fail",
    "todo", "next step", "will need", "should", "must not",
    "important", "critical", "note:", "caveat", "warning",
})

_WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
_READ_TOOLS  = {"Read", "Glob", "Grep"}


def _dedup(lst: list[str]) -> list[str]:
    return list(dict.fromkeys(lst))


def _read_tail_lines(path: Path, max_lines: int) -> list[str]:
    """Read the last `max_lines` from a file without loading it entirely."""
    try:
        size = path.stat().st_size
    except OSError:
        return []

    # Small files: read all at once.
    if size < 5 * 1024 * 1024:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-max_lines:]

    # Large files: scan backwards in 64KB chunks to find enough newlines.
    with path.open("rb") as f:
        f.seek(0, 2)
        chunks: list[bytes] = []
        pos = size
        newline_count = 0
        chunk_size = 65536
        while pos > 0 and newline_count < max_lines + 1:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)
            newline_count += chunk.count(b"\n")
            chunks.append(chunk)
    chunks.reverse()
    return b"".join(chunks).decode("utf-8", errors="ignore").splitlines()[-max_lines:]


def _parse_transcript(transcript_path: str, max_tail: int = 400) -> dict[str, Any]:
    """
    Parse the last `max_tail` lines of the JSONL transcript.

    Returns a dict with files_edited, files_read, bash_commands,
    recent_user_messages, decision_lines, error_lines.
    Returns {} only when the file is missing; returns the keyed dict
    (possibly with empty lists) when the file exists but has nothing parseable.
    """
    path = Path(transcript_path)
    if not path.exists():
        return {}

    lines = _read_tail_lines(path, max_tail)

    entries: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    files_edited: list[str] = []
    files_read: list[str] = []
    bash_commands: list[str] = []
    user_messages: list[str] = []
    decision_lines: list[str] = []
    error_lines: list[str] = []

    for entry in entries:
        msg = entry.get("message", {})
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        content = msg.get("content", [])

        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")

            if btype == "tool_use":
                tool_name = block.get("name", "")
                tool_input = block.get("input") or {}
                if not isinstance(tool_input, dict):
                    continue

                if tool_name in _WRITE_TOOLS:
                    fp = str(tool_input.get("file_path") or "").strip()
                    if fp:
                        files_edited.append(fp)
                elif tool_name in _READ_TOOLS:
                    fp = str(
                        tool_input.get("file_path")
                        or tool_input.get("pattern")
                        or tool_input.get("path")
                        or ""
                    ).strip()
                    if fp:
                        files_read.append(fp)
                elif tool_name == "Bash":
                    cmd = str(tool_input.get("command") or "").strip()
                    if cmd and not cmd.startswith("#"):
                        bash_commands.append(cmd[:200])

            elif btype == "text":
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                if role == "user" and len(text) > 12:
                    user_messages.append(text[:500])
                elif role == "assistant":
                    for sentence in text.replace("\n", " ").split(". "):
                        s = sentence.strip()
                        if len(s) < 25:
                            continue
                        sl = s.lower()
                        if any(kw in sl for kw in _DECISION_KW):
                            if any(w in sl for w in ("error", "fail", "exception", "bug", "issue", "problem")):
                                error_lines.append(s[:220])
                            else:
                                decision_lines.append(s[:220])

    deduped_edited = _dedup(files_edited)
    edited_set = set(deduped_edited)

    return {
        "files_edited": deduped_edited[-20:],
        "files_read": [f for f in _dedup(files_read)[-10:] if f not in edited_set],
        "bash_commands": _dedup(bash_commands)[-15:],
        "recent_user_messages": user_messages[-5:],
        "decision_lines": decision_lines[-20:],
        "error_lines": error_lines[-10:],
        "total_entries_parsed": len(entries),
    }


def _md_section(header: str, items: list[str], fmt: str = "- {}", limit: int | None = None) -> list[str]:
    """Render a markdown list section, or nothing if items is empty."""
    if not items:
        return []
    shown = items[-limit:] if limit else items
    return [f"### {header}"] + [fmt.format(x) for x in shown] + [""]


def _format_additional_context(snapshot: dict[str, Any]) -> str:
    """Render the snapshot as a concise markdown block for additionalContext injection."""
    parts: list[str] = [
        "## u-mem: Pre-Compact Session Snapshot",
        "*(Auto-saved by u-mem before context compaction. "
        "Call `mem_resume_task` or `mem_compact_snapshot` for full details.)*",
        "",
    ]

    if current_task := str(snapshot.get("current_task") or "").strip():
        parts += [f"### Active task\n{current_task[:400]}", ""]

    parts += _md_section("Files modified this session", snapshot.get("files_edited", []), fmt="- `{}`")
    parts += _md_section("Commands run", snapshot.get("bash_commands", []), fmt="- `{}`", limit=8)
    parts += _md_section("Key decisions / context", snapshot.get("decision_lines", []), limit=10)
    parts += _md_section("Errors / issues encountered", snapshot.get("error_lines", []), limit=5)

    if msgs := snapshot.get("recent_user_messages"):
        parts += [f"### Last user request\n{msgs[-1][:350]}", ""]

    return "\n".join(parts)


def _save_to_umem(snapshot: dict[str, Any], session_id: str, project: str) -> None:
    """Save high-signal lines from the snapshot as searchable memories."""
    try:
        from umem.config import get_db_path
        from umem.database import Database
    except ImportError:
        return  # fast-restore file still works without DB

    db = None
    try:
        db = Database(get_db_path())
        for line in snapshot.get("decision_lines", [])[-8:] + snapshot.get("error_lines", [])[-4:]:
            if len(line) < 30:
                continue
            try:
                db.save(
                    f"[session] {line}",
                    project=project,
                    session_id=session_id,
                    importance=3,
                    tags=["pre-compact", "auto-saved"],
                )
            except Exception:
                pass
    except Exception as exc:
        print(f"u-mem pre-compact: DB save failed: {exc}", file=sys.stderr)
    finally:
        if db is not None:
            db.close()


def main() -> None:
    data = read_stdin_json()

    session_id = str(data.get("session_id") or uuid.uuid4().hex[:16])
    transcript_path = str(data.get("transcript_path") or "")
    trigger = str(data.get("trigger") or "auto")
    cwd = str(Path(data.get("cwd") or os.getcwd()).resolve())

    from umem.config import detect_project
    project = detect_project(cwd) or "global"

    snapshot: dict[str, Any] = {}
    if transcript_path:
        try:
            snapshot = _parse_transcript(transcript_path)
        except Exception as exc:
            print(f"u-mem pre-compact: transcript parse error: {exc}", file=sys.stderr)

    # Enrich snapshot with metadata (single timestamp shared across both writes).
    saved_at = time.time()
    if snapshot:
        if snapshot.get("recent_user_messages"):
            snapshot["current_task"] = snapshot["recent_user_messages"][-1][:400]
        snapshot.update(
            project=project,
            session_id=session_id,
            trigger=trigger,
            cwd=cwd,
            saved_at=saved_at,
        )

    # Write fast-restore file (read by SessionStart hook after compact).
    restore_file = compact_restore_path(cwd)
    try:
        restore_file.parent.mkdir(parents=True, exist_ok=True)
        restore_file.write_text(
            json.dumps(
                {
                    "snapshot": snapshot,
                    "additional_context": _format_additional_context(snapshot),
                    "project": project,
                    "cwd": cwd,
                    "saved_at": saved_at,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"u-mem pre-compact: restore file write failed: {exc}", file=sys.stderr)

    # DB save is fire-and-forget — must never block or crash the compact.
    if snapshot:
        _save_to_umem(snapshot, session_id, project)

    sys.exit(0)


if __name__ == "__main__":
    main()
