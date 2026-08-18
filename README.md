# wakayo (我が世)

**Local memory store for AI agents — one world, two editors.**

```
pip install wakayo
```

```
wakayo add     --content "..." [--source opencode|hermes|manual] [--tags t1,t2] [--expires-days 30]
wakayo query   "search text" [--source ...] [--tags ...] [--after 2026-08-17] [--before 2026-08-18] [--limit 20] [--json]
wakayo list    [--source ...] [--limit 20] [--json]
wakayo get     <id>
wakayo promote <id>            # curated entry → ~/MEMORY.md (§-delimited)
wakayo compact                  # expire stale entries
wakayo stats
wakayo export [--path FILE]    # dump all entries to markdown
```

---

## what it is

wakayo is a **local, file-backed SQLite store** with full-text search and a lifecycle that decides what lives, what fades, and what gets curated. it's the memory layer a set of AI agents share — Hermes and opencode are two interfaces to the same brain.

it is **not** a service, not a vector store, not a managed memory provider. it's a file, a CLI, and a lifecycle tick. no Ollama, no Qdrant, no embeddings, no external dependency. inspectable with `sqlite3`, backs up with everything else.

## the world

wokoyo (我が世) is the world the agents inhabit together. captures are born, they either mature into something worth keeping or expire and fade, and the curated ones get promoted back to the durable read layer. nothing sits in an "everything I've ever said" bucket.

the memory model has two layers:

- **runtime memory** — the SQLite store. episodic captures, source-tagged, with optional TTL. this is what the CLI reads and writes. this is what opencode and Hermes share.
- **durable on-demand read layer** — `~/MEMORY.md` and the all-caps config files (`USER.md`, `AGENTS.md`, `SOUL.md`, etc.). standing identity, rules, and curated state. read on demand, not in every context. the store promotes curated entries back here.

the two layers are separate by design. the store is for runtime memory; the files are for standing state. you don't merge them.

## lifecycle

lifecycle is a **separate local tick** (launchd or cron) — not part of the pip package, because it's a machine-local concern. the pattern:

1. **expire** — `wakayo compact` deletes entries past their `expires_at`.
2. **compact** — optionally dedupe near-duplicates (future).
3. **promote** — curated entries get promoted to `~/MEMORY.md` via `wakayo promote <id>`.

a launchd `StartCalendarInterval` tick once a day runs the sweep. the tick is machine-local; the repo documents the pattern.

## query

FTS5 over the content. filters by source, tags, date range, limit. results are readable by default, JSON with `--json`. no embeddings, no semantic search — just text search over what was actually stored. if you want semantic later, that's an adapter on top, not a change to the store.

## editor integration

the CLI is the shared interface. both editors call the same thing.

- **opencode** — bash out to `wakayo add/query/...` or wrap the CLI as a tiny MCP server (you already load MCP servers — playwright is in your `opencode.json`).
- **Hermes** — call the CLI via the terminal tool, or wrap it as a `memory.provider` plugin under `plugins/memory/` for native integration.

the CLI is editor-agnostic. the wrappers are thin.

## storage

defaults to `~/.local/share/wakayo/memory.db` (XDG, portable; overridable via `WAKAYO_DIR`). SQLite + WAL. FTS5 virtual table over content. metadata columns: `source`, `tags`, `created_at`, `expires_at`, `promoted`. atomic writes via transactions; FTS5 stays in sync via triggers.

## license

MIT.

## status

seed / MVP. schema + CLI + lifecycle pattern are real; the Hermes `memory.provider` wrapper and opencode MCP wrapper are documented as examples first, deeper integration second.
