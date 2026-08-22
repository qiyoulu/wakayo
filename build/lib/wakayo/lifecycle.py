"""Lifecycle operations over the wakayo store.

The lifecycle is a local tick (launchd/cron), not part of the pip package.
It composes wakayo CLI commands or calls store functions directly.

Pattern (daily):
1. compact — expire stale entries
2. (future) dedupe near-duplicates
3. promote — curated entries → ~/MEMORY.md
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from wakayo.store import db_path, connect, init_db, compact as store_compact


def ensure_db(env: str | None = None) -> sqlite3.Connection:
    path = db_path(env)
    conn = connect(path)
    init_db(conn)
    return conn


def sweep_compact(env: str | None = None) -> int:
    """Run the compact step of the lifecycle. Returns count deleted."""
    conn = ensure_db(env)
    try:
        return store_compact(conn)
    finally:
        conn.close()


def sweep_promote_candidate(
    conn: sqlite3.Connection,
    min_age_days: int = 7,
    min_importance: Optional[float] = None,
) -> list[int]:
    """Return ids of entries that are candidates for promotion.

    MVP: entries old enough and not yet promoted. Importance scoring and
    the promotion gate are future work — for now it's age + not-yet-promoted.
    """
    import time

    cutoff = time.time() - min_age_days * 86400.0
    rows = conn.execute(
        """
        SELECT id FROM episodic
        WHERE promoted = 0
          AND created_at <= ?
        ORDER BY created_at ASC
        LIMIT 50
        """,
        (cutoff,),
    ).fetchall()
    return [r["id"] for r in rows]


def confirm_promotion(conn: sqlite3.Connection, entry_id: int) -> bool:
    """Check whether an entry is already promoted."""
    row = conn.execute(
        "SELECT promoted FROM episodic WHERE id = ?", (entry_id,)
    ).fetchone()
    return bool(row and row["promoted"])
