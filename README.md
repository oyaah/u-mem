# u-mem

Persistent memory for Claude Code. Survives compaction. Zero cloud.

```
pip install u-mem
u-mem-setup --mcp --hooks
```

That's it. Every Claude Code session now has memory.

---

## The problem

Claude Code forgets everything when the context window compacts — which it does silently, mid-task. You come back after a break, open a project, and Claude asks you to re-explain the architecture you walked through two hours ago. Every. Single. Time.

Without u-mem:
- You describe your auth system on Monday. Wednesday it's gone.
- You decide on a pattern ("always use the repository layer, never query from controllers"). Gone after first compaction.
- You debug a nasty SQLite locking bug for 40 minutes. Compact. You'll debug it again.
- You paste the same context paragraph at the start of every session.

With u-mem:
- Claude opens your project and already knows your recent decisions.
- When a compact fires, your session state is checkpointed automatically.
- After the compact, Claude picks up exactly where it left off.
- No tool calls required. It happens in the background.

---

## How it works

**SQLite + FTS5** stores memories locally at `~/.umem/memories.db`. No cloud, no API keys, no data leaving your machine. BM25 full-text search (same algorithm as Elasticsearch) with a Porter stemmer — "decided" matches "decision", "using" matches "used". Lookup is fast because it's an indexed virtual table, not a `LIKE '%query%'` scan.

**MCP (Model Context Protocol)** exposes five tools to Claude via stdio transport. Claude calls them; u-mem reads/writes the SQLite database. This is the same protocol Anthropic built for tool-use extensibility — it means u-mem also works with Cursor, Windsurf, Codex, and Gemini CLI, not just Claude Code.

**Hooks** are where the magic is. Claude Code fires `PreCompact` before it compacts the context, and `SessionStart` on every session. u-mem hooks into both:

```
PreCompact  →  reads the JSONL transcript → extracts files you edited,
               commands you ran, decisions you made, the last thing you
               asked for → writes a structured snapshot to ~/.umem/compacts/

SessionStart → if post-compact: injects that snapshot back as additionalContext
               so Claude wakes up knowing exactly where it was
             → if normal start: injects your 8 most recent project memories
               so relevant context is always present without any tool call
```

The cwd is hashed (`sha256[:16]`) to key the compact snapshot per-project, so opening project A never injects project B's state.

---

## Install

Requires Python 3.11+.

```bash
pip install u-mem
u-mem-setup --mcp --hooks
```

`--mcp` adds u-mem to `~/.claude/mcp.json` so Claude can call the memory tools.
`--hooks` registers the PreCompact and SessionStart hooks in `~/.claude/settings.json`.

Restart Claude Code after setup.

To verify:
```bash
u-mem-setup --status
```

---

## Tools

Claude gets five tools:

| Tool | What it does |
|---|---|
| `mem_save` | Save a memory (decision, fact, context) with optional tags and importance 1–5 |
| `mem_search` | BM25 full-text search across memories. Returns compact previews |
| `mem_get` | Fetch full content for specific IDs from search results |
| `mem_recent` | Most recent memories, newest first. Good for quick context bootstrap |
| `mem_compact_snapshot` | Read the pre-compact session checkpoint for manual recovery |

Memories are scoped to projects (auto-detected from git root) or global.

---

## Usage

Tell Claude what to remember:

> "remember that we're using the repository pattern here — controllers never query the DB directly"

> "save that the auth token lives in X-Auth-Token header, not Authorization"

> "note: the test database needs to be reset before the integration suite runs"

Claude calls `mem_save` and it persists across sessions, compactions, and restarts.

Search your own memory:
> "what did we decide about caching?"

Claude calls `mem_search("caching")` and surfaces what it saved.

---

## Project-scoped memory

u-mem detects your project from the git root. Memories saved in `/my-app` stay in `/my-app`. The SessionStart hook only injects memories for the current project — you won't see your other project's context bleed in.

You can also save global memories (no project scope) for things that apply everywhere:

```python
# Claude calls this
mem_save("always use UTC for timestamps", project="global", importance=5)
```

---

## What gets checkpointed before a compact

The PreCompact hook parses the JSONL transcript and extracts:

- Files you edited (from `Edit`, `Write`, `NotebookEdit` tool calls)
- Bash commands you ran
- Decision sentences from Claude's responses (filtered by keywords: "decided", "because", "fixed", "resolved", "important", etc.)
- Error lines (sentences mentioning bugs, exceptions, failures)
- Your last user message (treated as the active task)

This structured snapshot is written to `~/.umem/compacts/{cwd_hash}.json` and read back immediately after compaction via the SessionStart hook.

---

## Data

Everything lives at `~/.umem/`. Nothing goes anywhere else.

```
~/.umem/
  memories.db        # SQLite database (WAL mode)
  compacts/          # Per-project compact snapshots
```

---

## License

MIT
