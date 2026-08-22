"""SQLite-backed episodic memory store with FTS5 search.

Two tables:
- episodic: the source of truth (id, content, source, tags, created_at, expires_at, promoted)
- episodic_fts: FTS5 virtual table over content, kept in sync via triggers

All mutations go through a connection with transactions enabled. FTS5
stays in sync with the content table via AFTER INSERT/UPDATE/DELETE triggers.

Tags are stored as a comma-separated TEXT for the MVP. Filtering uses a
normalised LIKE so partial matches don't false-positive (e.g. "art" won't
match "_startup"). A proper tags table is future work.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

DB_FILENAME = "memory.db"


def wakayo_dir(env: Optional[str] = None) -> Path:
    """Resolve the wakayo data directory.

    WAKAYO_DIR env var overrides; default is XDG-local
    (~/.local/share/wakayo/). created on demand.
    """
    base = Path(env) if env else Path.home() / ".local" / "share" / "wakayo"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path(env: Optional[str] = None) -> Path:
    return wakayo_dir(env) / DB_FILENAME


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create episodic + FTS5 tables and sync triggers if they don't exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS episodic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            tags TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            expires_at REAL,
            promoted INTEGER NOT NULL DEFAULT 0
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(content);

        CREATE TRIGGER IF NOT EXISTS episodic_ai AFTER INSERT ON episodic BEGIN
            INSERT INTO episodic_fts(episodic_fts, rowid, content)
            VALUES ('insert', new.id, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS episodic_ad AFTER DELETE ON episodic BEGIN
            INSERT INTO episodic_fts(episodic_fts, rowid)
            VALUES ('delete', old.id);
        END;

        CREATE TRIGGER IF NOT EXISTS episodic_au AFTER UPDATE ON episodic
            WHEN old.content != new.content
        BEGIN
            INSERT INTO episodic_fts(episodic_fts, rowid)
            VALUES ('delete', old.id);
            INSERT INTO episodic_fts(episodic_fts, rowid, content)
            VALUES ('insert', new.id, new.content);
        END;
        """
    )
    conn.commit()


def now_ts() -> float:
    return time.time()


def add_entry(
    conn: sqlite3.Connection,
    content: str,
    source: str = "manual",
    tags: str = "",
    expires_after_days: Optional[int] = None,
) -> int:
    """Insert an episodic entry. Returns the new row id."""
    created_at = now_ts()
    expires_at = None
    if expires_after_days is not None and expires_after_days > 0:
        expires_at = created_at + expires_after_days * 86400.0

    tags = tags.strip()
    if tags.endswith(","):
        tags = tags[:-1]

    cur = conn.execute(
        """
        INSERT INTO episodic (content, source, tags, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (content, source, tags, created_at, expires_at),
    )
    conn.commit()
    return cur.lastrowid


def _tag_like(tag: str) -> str:
    """Return a WHERE clause fragment that matches the tag exactly.

    Uses ',tag,' normalisation so 'art' doesn't match '_startup'.
    Empty tags → no match.
    """
    tag = tag.strip()
    if not tag:
        return "1=0"
    return "(',' || tags || ',') LIKE ('%,' || ? || ',%')"


def query(
    conn: sqlite3.Connection,
    text: str,
    source: Optional[str] = None,
    tags: Optional[str] = None,
    after: Optional[float] = None,
    before: Optional[float] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """FTS5 search over content, with optional filters."""
    if not text.strip():
        return []

    conditions: list[str] = ["episodic_fts MATCH ?"]
    params: list[Any] = [text]

    if source:
        conditions.append("episodic.source = ?")
        params.append(source)

    if tags:
        conditions.append(_tag_like(tags))
        params.append(tags)

    if after is not None:
        conditions.append("episodic.created_at >= ?")
        params.append(after)

    if before is not None:
        conditions.append("episodic.created_at <= ?")
        params.append(before)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""
        SELECT episodic.*
        FROM episodic
        JOIN episodic_fts ON episodic.id = episodic_fts.rowid
        WHERE {where}
        ORDER BY episodic.created_at DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()

    return [dict(r) for r in rows]


def list_entries(
    conn: sqlite3.Connection,
    source: Optional[str] = None,
    after: Optional[float] = None,
    before: Optional[float] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Recent entries, optionally filtered."""
    conditions: list[str] = []
    params: list[Any] = []

    if source:
        conditions.append("source = ?")
        params.append(source)

    if after is not None:
        conditions.append("created_at >= ?")
        params.append(after)

    if before is not None:
        conditions.append("created_at <= ?")
        params.append(before)

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"""
        SELECT *
        FROM episodic
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()
    return [dict(r) for r in rows]


def get_entry(conn: sqlite3.Connection, entry_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute("SELECT * FROM episodic WHERE id = ?", (entry_id,)).fetchone()
    return dict(row) if row else None


def promote_entry(
    conn: sqlite3.Connection,
    entry_id: int,
    memory_md_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Mark an entry as promoted in the DB only.

    Promotion is now a pure DB flag (promoted=1) — it no longer writes
    to ~/MEMORY.md.  The old file-append behavior was removed because it
    let the standing layer grow unbounded.  The lifecycle tick can still
    use the promoted flag for selection; whichever consumer reads it
    decides whether to surface the content.
    """
    row = get_entry(conn, entry_id)
    if row is None:
        raise ValueError(f"no entry with id={entry_id}")

    conn.execute("UPDATE episodic SET promoted = 1 WHERE id = ?", (entry_id,))
    conn.commit()
    return row


def _promotion_block(row: dict[str, Any]) -> str:
    source = row.get("source", "manual")
    tags = row.get("tags", "")
    created = row.get("created_at", 0)
    content = row.get("content", "")
    import datetime

    ts = datetime.datetime.fromtimestamp(created, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    tag_line = f"  from: {source}" + (f" | tags: {tags}" if tags else "")
    return (
        f"\n§\n"
        f"[promoted from wakayo id={row['id']} {ts}]\n"
        f"{tag_line}\n"
        f"\n{content}\n"
        f"§\n"
    )


def _append_atomic(path: Path, block: str) -> None:
    """Atomically append a block to a file via write to temp + rename.

    The read-then-write pattern has a TOCTTOU race. We write the new
    full content to a temp file in the same directory and rename over
    the target — rename is atomic on POSIX.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    new_content = block if not path.exists() else path.read_text() + block
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new_content)
    tmp.rename(path)


def compact(conn: sqlite3.Connection) -> int:
    """Delete expired entries. Returns count deleted."""
    now = now_ts()
    cur = conn.execute(
        "DELETE FROM episodic WHERE expires_at IS NOT NULL AND expires_at <= ?",
        (now,),
    )
    conn.commit()
    return cur.rowcount


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) AS c FROM episodic").fetchone()["c"]
    chars = conn.execute("SELECT SUM(LENGTH(content)) AS c FROM episodic").fetchone()["c"] or 0
    expired = conn.execute(
        "SELECT COUNT(*) AS c FROM episodic WHERE expires_at IS NOT NULL AND expires_at <= ?",
        (now_ts(),),
    ).fetchone()["c"]
    promoted = conn.execute(
        "SELECT COUNT(*) AS c FROM episodic WHERE promoted = 1"
    ).fetchone()["c"]
    by_source = conn.execute(
        "SELECT source, COUNT(*) AS c FROM episodic GROUP BY source ORDER BY c DESC"
    ).fetchall()
    return {
        "total": total,
        "total_chars": chars,
        "expired": expired,
        "promoted": promoted,
        "by_source": [(r["source"], r["c"]) for r in by_source],
    }


def export_markdown(conn: sqlite3.Connection, path: Optional[Path] = None) -> str:
    """Dump all entries to markdown."""
    rows = conn.execute(
        "SELECT * FROM episodic ORDER BY created_at DESC"
    ).fetchall()
    lines: list[str] = []
    lines.append("# wakayo export")
    lines.append("")
    lines.append(f"generated: {time.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"total entries: {len(rows)}")
    lines.append("")
    for r in rows:
        lines.append(f"## id={r['id']}  ({r['source']})")
        if r["tags"]:
            lines.append(f"tags: {r['tags']}")
        import datetime

        ts = datetime.datetime.fromtimestamp(r["created_at"], tz=datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        lines.append(f"created: {ts}")
        if r["expires_at"]:
            lines.append(f"expires: {datetime.datetime.fromtimestamp(r['expires_at'], tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        if r["promoted"]:
            lines.append("promoted: yes")
        lines.append("")
        lines.append(r["content"])
        lines.append("")
        lines.append("§")
        lines.append("")
    body = "\n".join(lines)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return body
