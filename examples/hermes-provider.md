# wakayo + Hermes: two integration paths

Hermes can write to wakayo through either of these. pick one; you don't need both.

## path A — CLI via terminal (simplest, shared with opencode)

Hermes calls the `wakayo` CLI from the terminal tool. same interface opencode uses.

```
terminal(command="wakayo add --content '...' --source hermes --tags skillit,design --expires-days 90")
```

query:

```
terminal(command="wakayo query 'promotion gate' --source hermes --json")
```

this is the lowest-friction path. both editors call the same CLI → same brain.

## path B — native memory.provider wrapper (tighter, optional)

Hermes has a pluggable `memory.provider` system. you can wrap wakayo as a provider
under `plugins/memory/` so Hermes's native `memory` tool writes to the store.

sketch (the provider skeleton):

```
plugins/memory/
└── __init__.py          # registers the provider via register_memory_provider()
```

the provider implements the `MemoryProvider` interface (add / replace / remove /
query) and delegates to the wakayo store — either by calling the CLI or by
importing `wakayo.store` directly and using the SQLite connection.

when `memory.provider` is set to the wakayo provider in `config.yaml`, Hermes's
memory tool routes through it. the built-in file-backed store (`~/.hermes/memories/`)
stays dormant or retired.

this is deeper integration. start with path A; move to B if the CLI feels too
remote from Hermes's memory tool.

## where wakayo sits relative to Hermes's existing memory

Hermes already has a file-backed memory store (`~/.hermes/memories/MEMORY.md` +
`USER.md`, §-delimited, char-limited). wakayo is a different layer:

- Hermes built-in store → `~/.hermes/memories/` (Hermes-authored, char-limited)
- wakayo → `~/.local/share/wakayo/memory.db` (editor-agnostic, FTS5, lifecycle)

if you want one consolidated store, point both Hermes and opencode at wakayo and
leave the Hermes built-in store dormant. if you want Hermes-authored memory to
stay in its own store and only shared memory to go through wakayo, run both.

the decision is about consolidation vs. separation, not about capability.
