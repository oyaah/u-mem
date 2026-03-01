"""End-to-end tests for u-mem product server (5 tools)."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest


class TestMemSave:
    def test_saves_and_returns_id(self, isolated_server):
        r = isolated_server.mem_save(content="decided to use SQLite over Postgres", project="proj")
        assert r["saved"] is True
        assert len(r["id"]) == 16
        assert r["project"] == "proj"

    def test_deduplicates_same_content(self, isolated_server):
        r1 = isolated_server.mem_save(content="same content", project="proj")
        r2 = isolated_server.mem_save(content="same content", project="proj", importance=5)
        assert r1["id"] == r2["id"]

    def test_clamps_importance(self, isolated_server):
        r = isolated_server.mem_save(content="test", importance=99)
        assert r["saved"] is True  # didn't raise

    def test_auto_detects_project(self, isolated_server):
        r = isolated_server.mem_save(content="auto project test")
        assert r["project"]  # some string, not empty


class TestMemSearch:
    def test_finds_saved_memory(self, isolated_server):
        isolated_server.mem_save(content="PostgreSQL connection pooling strategy", project="db")
        r = isolated_server.mem_search(query="PostgreSQL", project="db")
        assert r["count"] >= 1
        assert any("PostgreSQL" in res["preview"] for res in r["results"])

    def test_returns_id_for_mem_get(self, isolated_server):
        saved = isolated_server.mem_save(content="important decision about caching", project="p")
        found = isolated_server.mem_search(query="caching", project="p")
        assert found["results"][0]["id"] == saved["id"]

    def test_project_filter_works(self, isolated_server):
        isolated_server.mem_save(content="redis for caching", project="proj-a")
        isolated_server.mem_save(content="memcached for caching", project="proj-b")
        r = isolated_server.mem_search(query="caching", project="proj-a")
        assert all(res["project"] == "proj-a" for res in r["results"])

    def test_no_project_searches_all(self, isolated_server):
        isolated_server.mem_save(content="alpha project fact", project="alpha")
        isolated_server.mem_save(content="beta project fact", project="beta")
        r = isolated_server.mem_search(query="project fact")
        assert r["count"] >= 2

    def test_clamps_limit(self, isolated_server):
        for i in range(5):
            isolated_server.mem_save(content=f"fact number {i} about caching", project="lim")
        r = isolated_server.mem_search(query="fact caching", project="lim", limit=2)
        assert len(r["results"]) <= 2

    def test_returns_preview_not_full_content(self, isolated_server):
        long = "architecture " * 40  # 520 chars, highly searchable
        isolated_server.mem_save(content=long, project="p")
        r = isolated_server.mem_search(query="architecture", project="p")
        assert r["count"] >= 1
        assert len(r["results"][0]["preview"]) <= 150


class TestMemGet:
    def test_returns_full_content(self, isolated_server):
        long = "decided: " + "x" * 400
        saved = isolated_server.mem_save(content=long, project="p")
        r = isolated_server.mem_get(ids=[saved["id"]])
        assert r["count"] == 1
        assert r["memories"][0]["content"] == long

    def test_returns_tags(self, isolated_server):
        saved = isolated_server.mem_save(content="tagged memory", project="p", tags=["bug", "fix"])
        r = isolated_server.mem_get(ids=[saved["id"]])
        assert set(r["memories"][0]["tags"]) == {"bug", "fix"}

    def test_empty_ids_returns_empty(self, isolated_server):
        r = isolated_server.mem_get(ids=[])
        assert r["count"] == 0

    def test_missing_id_silently_skipped(self, isolated_server):
        r = isolated_server.mem_get(ids=["nonexistent0000000"])
        assert r["count"] == 0

    def test_preserves_order(self, isolated_server):
        ids = [isolated_server.mem_save(content=f"memory {i}", project="p")["id"] for i in range(3)]
        r = isolated_server.mem_get(ids=ids)
        returned_ids = [m["id"] for m in r["memories"]]
        assert returned_ids == ids


class TestMemRecent:
    def test_returns_most_recent_first(self, isolated_server):
        isolated_server.mem_save(content="first memory", project="p")
        time.sleep(0.01)
        isolated_server.mem_save(content="second memory", project="p")
        r = isolated_server.mem_recent(project="p", limit=2)
        assert r["memories"][0]["preview"].startswith("second")

    def test_project_filter(self, isolated_server):
        isolated_server.mem_save(content="proj-a memory", project="proj-a")
        isolated_server.mem_save(content="proj-b memory", project="proj-b")
        r = isolated_server.mem_recent(project="proj-a")
        assert all(m["project"] == "proj-a" for m in r["memories"])

    def test_limit_respected(self, isolated_server):
        for i in range(10):
            isolated_server.mem_save(content=f"memory {i}", project="p")
        r = isolated_server.mem_recent(project="p", limit=3)
        assert len(r["memories"]) == 3

    def test_no_project_returns_all(self, isolated_server):
        isolated_server.mem_save(content="alpha", project="a")
        isolated_server.mem_save(content="beta", project="b")
        r = isolated_server.mem_recent()
        assert r["count"] >= 2


class TestMemCompactSnapshot:
    def test_no_restore_file_returns_found_false(self, isolated_server, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        r = isolated_server.mem_compact_snapshot()
        assert r["found"] is False
        assert "hint" in r

    def test_reads_restore_file(self, isolated_server, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))

        # Compute the cwd_hash the same way the server does (Path.cwd().resolve())
        from umem.hooks.utils import compact_restore_path
        cwd = str(Path.cwd().resolve())
        restore_file = tmp_path / ".umem" / "compacts" / f"{hashlib.sha256(cwd.encode()).hexdigest()[:16]}.json"
        restore_file.parent.mkdir(parents=True)
        restore_file.write_text(json.dumps({
            "snapshot": {
                "files_edited": ["server.py", "database.py"],
                "bash_commands": ["pytest -q"],
                "decision_lines": ["decided SQLite over Postgres"],
                "error_lines": [],
                "current_task": "fix the snapshot test",
            },
            "additional_context": "## Context\nFix tests",
            "project": "testproj",
            "cwd": cwd,
            "saved_at": 1700000000.0,
        }))

        r = isolated_server.mem_compact_snapshot()
        assert r["found"] is True
        assert r["current_task"] == "fix the snapshot test"
        assert "server.py" in r["files_edited"]
        assert r["project"] == "testproj"
