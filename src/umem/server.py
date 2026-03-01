from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import detect_project, get_db_path
from .database import Database
from .hooks.utils import compact_restore_path

mcp = FastMCP("u-mem")
_db: Database | None = None


def _get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(get_db_path())
    return _db


@mcp.tool()
def mem_save(
    content: str,
    project: str | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
) -> dict[str, Any]:
    """
    Save a memory. Content is plain text — a decision, fact, context, or note.

    project:    project name (auto-detected from git root if omitted)
    tags:       optional list of string tags for filtering
    importance: 1 (ephemeral) to 5 (critical), default 3
    """
    proj = project or detect_project()
    importance = max(1, min(5, importance))
    mem_id = _get_db().save(content, project=proj, tags=tags, importance=importance)
    return {"id": mem_id, "project": proj, "saved": True}


@mcp.tool()
def mem_search(
    query: str,
    project: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Search memories with BM25 full-text search. Returns compact results (~50 tokens each).
    Use mem_get to fetch full content for specific IDs.

    query:   natural language or keyword search
    project: filter by project (None = search all projects)
    limit:   max results, default 20
    """
    limit = max(1, min(50, limit))
    results = _get_db().search(query, project=project, limit=limit)
    return {
        "count": len(results),
        "results": [
            {
                "id": r["id"],
                "project": r["project"],
                "importance": r["importance"],
                "tags": r["tags"],
                "preview": r["content"][:120],
                "created_at": r["created_at"],
            }
            for r in results
        ],
    }


@mcp.tool()
def mem_get(ids: list[str]) -> dict[str, Any]:
    """
    Fetch full content for specific memory IDs (from mem_search results).
    """
    memories = _get_db().get_many(ids)
    return {"count": len(memories), "memories": memories}


@mcp.tool()
def mem_recent(
    project: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Return most recent memories, newest first. Good for session bootstrap.

    project: filter by project (None = all projects)
    limit:   max results, default 20
    """
    limit = max(1, min(50, limit))
    results = _get_db().recent(project=project, limit=limit)
    return {
        "count": len(results),
        "memories": [
            {
                "id": r["id"],
                "project": r["project"],
                "importance": r["importance"],
                "tags": r["tags"],
                "preview": r["content"][:200],
                "created_at": r["created_at"],
            }
            for r in results
        ],
    }


@mcp.tool()
def mem_compact_snapshot(project: str | None = None) -> dict[str, Any]:
    """
    Read the pre-compact session snapshot for the current project.

    Call this after compaction if the auto-injection didn't fire, or to re-read
    what was saved: files modified, commands run, decisions made, last task.

    Install hooks with `u-mem-setup --hooks` for automatic injection.
    """
    cwd = str(Path.cwd().resolve())
    restore_file = compact_restore_path(cwd)
    fast_restore: dict[str, Any] = {}
    try:
        fast_restore = json.loads(restore_file.read_text(encoding="utf-8"))
    except Exception:
        pass

    snapshot = fast_restore.get("snapshot") or {}
    additional_context = str(fast_restore.get("additional_context") or "").strip()

    if not snapshot and not additional_context:
        return {
            "found": False,
            "hint": "No snapshot found. Install hooks: `u-mem-setup --hooks`",
        }

    return {
        "found": True,
        "project": fast_restore.get("project"),
        "saved_at": fast_restore.get("saved_at"),
        "additional_context": additional_context,
        "files_edited": snapshot.get("files_edited", []),
        "bash_commands": snapshot.get("bash_commands", [])[-8:],
        "decision_lines": snapshot.get("decision_lines", [])[-10:],
        "error_lines": snapshot.get("error_lines", []),
        "current_task": snapshot.get("current_task", ""),
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
