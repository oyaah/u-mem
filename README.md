# u-mem 🧠

**Persistent memory for Claude Code. Survives compaction. Zero cloud. One command to install.**

```bash
pip install u-mem
u-mem-setup --mcp --hooks
```

Restart Claude Code. Done.

---

## The problem

Claude Code compacts the context window silently mid-session. When it does, everything you built up — architecture decisions, debugging context, your current task — is gone.

Without u-mem, you spend your time:
- 🔁 Re-explaining your project structure every few hours
- 😤 Re-debugging things you already solved
- 📋 Pasting the same context paragraphs at the start of every session
- 🤦 Watching Claude suggest the exact pattern you told it not to use

---

## What u-mem does

**Survives compaction** — hooks into Claude Code's lifecycle to checkpoint your session before the compact fires, then restores it automatically after. Claude wakes up knowing exactly where it left off.

**Passive context injection** — at every session start, your recent project memories are injected into Claude's context without any tool call. Claude already knows what you're working on when you open a project.

**Searchable memory** — tell Claude to save decisions, patterns, or facts. They persist across sessions, compactions, and restarts. Search them anytime.

---

## Install

```bash
pip install u-mem
u-mem-setup --mcp --hooks
```

> Requires Python 3.11+

`--mcp` wires u-mem into `~/.claude/mcp.json` so Claude can call the memory tools.
`--hooks` registers the PreCompact and SessionStart hooks in `~/.claude/settings.json`.

Verify setup:
```bash
u-mem-setup --status
```

---

## Usage

Tell Claude what to remember:

> *"Remember that we're using the repository pattern — controllers never query the DB directly"*

> *"Save that the auth token goes in X-Auth-Token, not Authorization"*

> *"Note: the integration test DB needs to be reset before the full suite"*

Recall it later:

> *"What did we decide about caching?"*

> *"What were we working on last session?"*

That's it. The compaction survival and session injection happen automatically in the background.

---

## How it works

### 🗄️ Storage — SQLite + FTS5

Memories live in `~/.umem/memories.db`. **FTS5** (SQLite's full-text search extension) gives BM25 relevance ranking with a Porter stemmer — "decided" matches "decision", "fixing" matches "fixed". Lookups are fast because it's an indexed virtual table, not a `LIKE '%..%'` scan.

Content-addressed IDs (`sha256[:16]`) make saves idempotent — saving the same memory twice is a no-op.

### 🔌 MCP — Model Context Protocol

Five tools are exposed to Claude over stdio. Claude calls them; u-mem reads/writes the database. Because it's standard MCP, it also works with **Cursor, Windsurf, Codex, and Gemini CLI** — not just Claude Code.

### 🪝 Hooks — the compaction survival layer

Two hooks do the real work:

```
PreCompact ──► reads JSONL transcript ──► extracts files edited, commands run,
               decisions made, current task ──► writes snapshot to ~/.umem/compacts/

SessionStart ─► post-compact: injects snapshot as additionalContext (Claude wakes up)
              ─► normal start: injects 8 most recent project memories (always in context)
```

The CWD is hashed (`sha256[:16]`) to key snapshots per-project. Opening project A never injects project B's state.

---

## Tools

| Tool | What it does |
|---|---|
| `mem_save` | Save a memory with optional tags and importance 1–5 |
| `mem_search` | BM25 full-text search. Returns compact previews |
| `mem_get` | Fetch full content for specific IDs |
| `mem_recent` | Most recent memories, newest first |
| `mem_compact_snapshot` | Read the pre-compact checkpoint for manual recovery |

---

## What gets checkpointed

Before every compaction, u-mem parses your session transcript and extracts:

- 📝 **Files you edited** — from `Edit`, `Write`, `NotebookEdit` tool calls
- 💻 **Commands you ran** — from `Bash` tool calls
- 🧭 **Decision sentences** — Claude responses mentioning "decided", "fixed", "important", "resolved", etc.
- ⚠️ **Error lines** — sentences mentioning bugs, exceptions, failures
- 🎯 **Your last message** — treated as the active task

This is what Claude reads when it comes back after a compact.

---

## Data & privacy

Everything lives at `~/.umem/`. Nothing leaves your machine.

```
~/.umem/
  memories.db      # SQLite database (WAL mode)
  compacts/        # Per-project compact snapshots
```

---

## License

MIT
