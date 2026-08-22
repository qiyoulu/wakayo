#!/usr/bin/env python3
"""wakayo CLI — local memory store for AI agents."""

from __future__ import annotations

import argparse
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

from wakayo.store import (
    db_path,
    connect,
    init_db,
    add_entry,
    query as store_query,
    list_entries as store_list,
    get_entry,
    promote_entry,
    compact as store_compact,
    stats as store_stats,
    export_markdown,
)


def _env_dir() -> str | None:
    return os.environ.get("WAKAYO_DIR")


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _print_result(entry: dict) -> None:
    print(f"[{entry['id']}] source={entry['source']} tags={entry['tags'] or '-'}")
    print(f"    created={_fmt_ts(entry['created_at'])}")
    if entry["expires_at"]:
        print(f"    expires={_fmt_ts(entry['expires_at'])}")
    if entry["promoted"]:
        print("    promoted=yes")
    print()
    print(entry["content"])
    print()


def _print_json(results: list[dict]) -> None:
    print(json.dumps(results, indent=2, default=str))


def get_conn(args: argparse.Namespace) -> __import__("sqlite3").Connection:
    path = db_path(_env_dir())
    conn = connect(path)
    init_db(conn)
    return conn


def cmd_add(args: argparse.Namespace) -> None:
    content = args.content
    if args.file:
        content = Path(args.file).read_text()
    elif content is None and not sys.stdin.isatty():
        content = sys.stdin.read()
    if not content:
        print("error: no content provided (use --content, --file, or stdin)", file=sys.stderr)
        sys.exit(1)

    conn = get_conn(args)
    try:
        eid = add_entry(
            conn,
            content=content,
            source=args.source or "manual",
            tags=args.tags or "",
            expires_after_days=args.expires_days,
        )
        print(f"added id={eid} source={args.source or 'manual'}")
        if args.expires_days:
            print(f"    expires in {args.expires_days} days")
    finally:
        conn.close()


def cmd_query(args: argparse.Namespace) -> None:
    after = _parse_ts(args.after)
    before = _parse_ts(args.before)

    conn = get_conn(args)
    try:
        results = store_query(
            conn,
            text=args.query,
            source=args.source,
            tags=args.tags,
            after=after,
            before=before,
            limit=args.limit,
        )
    finally:
        conn.close()

    if args.json:
        _print_json(results)
    else:
        if not results:
            print("no results")
            return
        for r in results:
            _print_result(r)


def cmd_list(args: argparse.Namespace) -> None:
    after = _parse_ts(args.after)
    before = _parse_ts(args.before)

    conn = get_conn(args)
    try:
        results = store_list(
            conn,
            source=args.source,
            after=after,
            before=before,
            limit=args.limit,
        )
    finally:
        conn.close()

    if args.json:
        _print_json(results)
    else:
        if not results:
            print("no entries")
            return
        for r in results:
            _print_result(r)


def cmd_get(args: argparse.Namespace) -> None:
    conn = get_conn(args)
    try:
        entry = get_entry(conn, args.id)
    finally:
        conn.close()

    if entry is None:
        print(f"no entry with id={args.id}", file=sys.stderr)
        sys.exit(1)
    _print_result(entry)


def cmd_promote(args: argparse.Namespace) -> None:
    conn = get_conn(args)
    try:
        entry = promote_entry(conn, args.id)
    finally:
        conn.close()
    print(f"promoted id={entry['id']} (flag set in DB only, no MEMORY.md write)")


def cmd_compact(args: argparse.Namespace) -> None:
    conn = get_conn(args)
    try:
        n = store_compact(conn)
    finally:
        conn.close()
    print(f"compacted {n} expired entries")


def cmd_stats(args: argparse.Namespace) -> None:
    conn = get_conn(args)
    try:
        s = store_stats(conn)
    finally:
        conn.close()

    print(f"total entries:   {s['total']}")
    print(f"total chars:     {s['total_chars']}")
    print(f"expired:         {s['expired']}")
    print(f"promoted:        {s['promoted']}")
    if s["by_source"]:
        print("by source:")
        for src, cnt in s["by_source"]:
            print(f"    {src:12} {cnt}")


def cmd_export(args: argparse.Namespace) -> None:
    conn = get_conn(args)
    try:
        body = export_markdown(conn, Path(args.path) if args.path else None)
    finally:
        conn.close()

    if args.path:
        print(f"exported to {args.path}")
    else:
        print(body)


def _parse_ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        print(f"warning: could not parse date {s!r}, ignoring", file=sys.stderr)
        return None


def main() -> None:
    p = argparse.ArgumentParser(
        prog="wakayo",
        description="我が世 — local memory store for AI agents",
    )
    p.set_defaults(func=lambda args: p.print_help())

    sub = p.add_subparsers(dest="command")

    # add
    a = sub.add_parser("add", help="add an episodic entry")
    a.add_argument("--content", help="entry content (single line)")
    a.add_argument("--file", help="read content from a file")
    a.add_argument("--source", choices=["opencode", "hermes", "manual"], default="manual")
    a.add_argument("--tags", help="comma-separated tags")
    a.add_argument("--expires-days", type=int, help="auto-expire after N days")
    a.set_defaults(func=cmd_add)

    # query
    q = sub.add_parser("query", help="FTS5 search")
    q.add_argument("query", help="search text")
    q.add_argument("--source", help="filter by source")
    q.add_argument("--tags", help="filter by tag")
    q.add_argument("--after", help="ISO datetime (inclusive)")
    q.add_argument("--before", help="ISO datetime (inclusive)")
    q.add_argument("--limit", type=int, default=20)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_query)

    # list
    l = sub.add_parser("list", help="recent entries")
    l.add_argument("--source", help="filter by source")
    l.add_argument("--after", help="ISO datetime (inclusive)")
    l.add_argument("--before", help="ISO datetime (inclusive)")
    l.add_argument("--limit", type=int, default=20)
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_list)

    # get
    g = sub.add_parser("get", help="get a single entry")
    g.add_argument("id", type=int)
    g.set_defaults(func=cmd_get)

    # promote
    pm = sub.add_parser("promote", help="mark an entry as promoted (DB flag only, no MEMORY.md write)")
    pm.add_argument("id", type=int)
    pm.set_defaults(func=cmd_promote)

    # compact
    c = sub.add_parser("compact", help="expire stale entries")
    c.set_defaults(func=cmd_compact)

    # stats
    s = sub.add_parser("stats", help="store statistics")
    s.set_defaults(func=cmd_stats)

    # export
    e = sub.add_parser("export", help="dump all entries to markdown")
    e.add_argument("--path", help="write to a file (default: stdout)")
    e.set_defaults(func=cmd_export)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
