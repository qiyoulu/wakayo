# wakayo

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

## What it is

Wakayo is a **local, file-backed SQLite store** with full-text search and a lifecycle that decides what lives, what fades, and what gets curated. It's the memory layer a set of AI agents share — Hermes and opencode are two interfaces to the same brain.

It is **not** a service, not a vector store, not a managed memory provider. It's a file, a CLI, and a lifecycle tick. No Ollama, no Qdrant, no embeddings, no external dependency. Inspectable with `sqlite3`, backs up with everything else.

## The world

Wakayo is the world the agents inhabit together. captures are born, they either mature into something worth keeping or expire and fade, and the curated ones get promoted back to the durable read layer. nothing sits in an "everything I've ever said" bucket.

The memory model has two layers:

- **Runtime memory** — the SQLite store. Episodic captures, source-tagged, with optional TTL. This is what the CLI reads and writes. This is what opencode and Hermes share.
- **Durable on-demand read layer** — `~/MEMORY.md` and the all-caps config files (`USER.md`, `AGENTS.md`, `SOUL.md`, etc.). Standing identity, rules, and curated state. Read on demand, not in every context. The store promotes curated entries back here.

The two layers are separate by design. The store is for runtime memory; the files are for standing state. You don't merge them.

## Lifecycle

Lifecycle is a **separate local tick** (launchd or cron) — not part of the pip package, because it's a machine-local concern. The pattern:

1. **Expire** — `wakayo compact` deletes entries past their `expires_at`.
2. **Compact** — optionally dedupe near-duplicates (future).
3. **Promote** — curated entries get promoted to `~/MEMORY.md` via `wakayo promote <id>`.

A launchd `StartCalendarInterval` tick once a day runs the sweep. The tick is machine-local; the repo documents the pattern.

## Query

FTS5 over the content. Filters by source, tags, date range, limit. Results are readable by default, JSON with `--json`. No embeddings, no semantic search — just text search over what was actually stored. If you want semantic later, that's an adapter on top, not a change to the store.

## Editor integration

The CLI is the shared interface. Both editors call the same thing.

- **opencode** — bash out to `wakayo add/query/...` or wrap the CLI as a tiny MCP server (you already load MCP servers — playwright is in your `opencode.json`).
- **Hermes** — call the CLI via the terminal tool, or wrap it as a `memory.provider` plugin under `plugins/memory/` for native integration.

The CLI is editor-agnostic. The wrappers are thin.

## Storage

Defaults to `~/.local/share/wakayo/memory.db` (XDG, portable; overridable via `WAKAYO_DIR`). SQLite + WAL. FTS5 virtual table over content. Metadata columns: `source`, `tags`, `created_at`, `expires_at`, `promoted`. Atomic writes via transactions; FTS5 stays in sync via triggers.

## License

MIT.

## Status

Seed / MVP. Schema + CLI + lifecycle pattern are real; the Hermes `memory.provider` wrapper and opencode MCP wrapper are documented as examples first, deeper integration second.

## Name

**wakayo** (我が世) comes from the *Iroha uta* (いろは歌), the classic Japanese pangram poem that arranges all kana in a single quatrain:

> いろはにほへとちりぬるを
> わかよたれそつねんころり
> うゐのおくやまさきすゑむ
> あせたちりぬるを

*わかよ* (*wakayo*) is the 8th–11th syllables of the second line: 我が世, "our world." It was chosen as the project name because this is the shared world both editors — Hermes and opencode — inhabit together.

There is a second reading: 若代 (*wakayo*, "young generation") — the generational hypothesis made literal, paralleling the Iroha reading. The store is the young generation (short-lived, swept by `wakayo compact`); the standing files (`~/MEMORY.md`, `USER.md`, `AGENTS.md`, `SOUL.md`) are the tenured space, promoted into via `wakayo_promote`. Most captures are ephemeral and should be collected fast; only the durable fraction is promoted. The mark-and-sweep pattern is the same one a generational garbage collector uses: mark the session as learned after the pipeline runs, then free the buffer.
