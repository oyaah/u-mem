# u-mem

Persistent memory for Claude Code. Survives compaction. Zero cloud.

```bash
pip install u-mem
u-mem-setup --mcp --hooks
```

---

## What it does

Claude Code compacts the context window when it fills up. When it does, whatever you were working on — decisions made, files edited, current task — is gone.

u-mem hooks into that lifecycle:

- **PreCompact** — reads your session transcript before compaction, extracts what you were doing, writes a local snapshot
- **SessionStart** — after compaction, injects that snapshot back so Claude picks up where it left off. On normal starts, injects your 8 most recent project memories

You can also save memories explicitly and search them later.

---

## Install

Requires Python 3.11+.

```bash
pip install u-mem
u-mem-setup --mcp --hooks
```

Restart Claude Code. Verify:

```bash
u-mem-setup --status
```

---

## Tools

| Tool | Description |
|---|---|
| `mem_save` | Save a memory with optional tags and importance 1–5 |
| `mem_search` | BM25 full-text search across memories |
| `mem_get` | Fetch full content for specific IDs |
| `mem_recent` | Most recent memories, newest first |
| `mem_compact_snapshot` | Read the pre-compact session checkpoint |

Memories are scoped per project (auto-detected from git root) or global.

---

## How it works

**Storage** — SQLite + FTS5 at `~/.umem/memories.db`. BM25 ranking with Porter stemmer. Content-addressed IDs so saving the same memory twice is an idempotent upsert. WAL mode for concurrent access.

**MCP** — tools exposed over stdio via FastMCP. Works with Cursor, Windsurf, Codex, and Gemini CLI in addition to Claude Code.

**Hooks** — `PreCompact` parses the JSONL transcript tail and extracts edited files, bash commands, decision sentences, error lines, and your last message. Writes to `~/.umem/compacts/{sha256(cwd)[:16]}.json`. `SessionStart` reads it back and injects as `additionalContext`.

---

## Data

Everything in `~/.umem/`. Nothing leaves your machine.

---

## License

MIT
