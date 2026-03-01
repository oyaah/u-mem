from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    project     TEXT NOT NULL DEFAULT 'global',
    session_id  TEXT,
    importance  INTEGER NOT NULL DEFAULT 3,
    content     TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_project ON memories(project);
CREATE INDEX IF NOT EXISTS idx_created ON memories(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    id UNINDEXED,
    content,
    tags,
    content='memories',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, id, content, tags)
    VALUES (new.rowid, new.id, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, id, content, tags)
    VALUES ('delete', old.rowid, old.id, old.content, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, id, content, tags)
    VALUES ('delete', old.rowid, old.id, old.content, old.tags);
    INSERT INTO memories_fts(rowid, id, content, tags)
    VALUES (new.rowid, new.id, new.content, new.tags);
END;
"""


def _id(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


class Database:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def save(self, content: str, project: str = "global", tags: list[str] | None = None,
             importance: int = 3, session_id: str | None = None) -> str:
        if not content.strip():
            raise ValueError("content must not be empty")
        mem_id = _id(content)
        now = time.time()
        tags_json = json.dumps(tags or [])
        if self._conn.execute("SELECT 1 FROM memories WHERE id=?", (mem_id,)).fetchone():
            self._conn.execute(
                "UPDATE memories SET updated_at=?, project=?, importance=?, tags=? WHERE id=?",
                (now, project, importance, tags_json, mem_id),
            )
        else:
            self._conn.execute(
                "INSERT INTO memories(id,created_at,updated_at,project,session_id,importance,content,tags) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (mem_id, now, now, project, session_id, importance, content, tags_json),
            )
        self._conn.commit()
        return mem_id

    def search(self, query: str, project: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if project:
            rows = self._conn.execute(
                """SELECT m.*, fts.rank FROM memories_fts fts
                   JOIN memories m ON m.id = fts.id
                   WHERE m.project=? AND memories_fts MATCH ?
                   ORDER BY fts.rank LIMIT ?""",
                (project, query, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT m.*, fts.rank FROM memories_fts fts
                   JOIN memories m ON m.id = fts.id
                   WHERE memories_fts MATCH ?
                   ORDER BY fts.rank LIMIT ?""",
                (query, limit),
            ).fetchall()
        return [_row(r) for r in rows]

    def get_many(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        rows = self._conn.execute(f"SELECT * FROM memories WHERE id IN ({ph})", ids).fetchall()
        by_id = {r["id"]: _row(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def recent(self, project: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if project:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE project=? ORDER BY created_at DESC LIMIT ?",
                (project, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
