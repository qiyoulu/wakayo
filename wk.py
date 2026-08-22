#!/usr/bin/env python3
"""wk — stdio MCP server wrapping the wakayo CLI for opencode.

opencode launches this as a subprocess and speaks JSON-RPC over stdin/stdout.
every tool call delegates to the wakayo CLI (which is on PATH / known location).
both editors — Hermes via the in-process provider, opencode via this MCP server —
hit the same SQLite store at ~/.local/share/wakayo/memory.db.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# locate the wakayo CLI — discoverable via PATH, not hardcoded to a venv
# ---------------------------------------------------------------------------
def _discover_wakayo_cli() -> str | None:
    """Find wakayo on PATH first; fall back to the Hermes venv for the
    current shared-install layout.  Set WAKAYO_CLI to override either."""
    on_path = shutil.which("wakayo")
    if on_path:
        return on_path
    # legacy fallback: the shared pip install in the Hermes venv.
    # this path is NOT the default any more — only used when wakayo isn't
    # on PATH and the shared install is still present.
    legacy = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "wakayo"
    if legacy.is_file():
        return str(legacy)
    return None


_WAKAYO_CLI = os.environ.get("WAKAYO_CLI") or _discover_wakayo_cli()
if _WAKAYO_CLI is None:
    sys.exit(
        "error: wakayo CLI not found. install wakayo (pip install wakayo) or "
        "set WAKAYO_CLI to the binary path."
    )
WAKAYO_CLI = _WAKAYO_CLI
WAKAYO_DIR = os.environ.get("WAKAYO_DIR") or str(Path.home() / ".local" / "share" / "wakayo")


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["WAKAYO_DIR"] = WAKAYO_DIR
    return env


def _run(*args: str) -> str:
    proc = subprocess.run(
        [WAKAYO_CLI, *args],
        capture_output=True,
        text=True,
        env=_env(),
        timeout=30,
    )
    if proc.returncode != 0:
        return f"error: {proc.stderr.strip()}"
    return proc.stdout.strip()


def _tool_add(args: dict) -> str:
    content = args.get("content", "").strip()
    if not content:
        return json.dumps({"error": "content is required"})
    source = args.get("source", "opencode") or "opencode"
    tags = args.get("tags", "") or ""
    expires = args.get("expires_days")
    cmd: list[str] = ["add", "--content", content, "--source", source]
    if tags:
        cmd.extend(["--tags", tags])
    if expires:
        cmd.extend(["--expires-days", str(expires)])
    return _run(*cmd)


def _tool_query(args: dict) -> str:
    q = args.get("query", "").strip()
    if not q:
        return json.dumps({"error": "query is required"})
    source = args.get("source")
    tags = args.get("tags")
    limit = args.get("limit", 20)
    cmd: list[str] = ["query", q, "--limit", str(limit), "--json"]
    if source:
        cmd.extend(["--source", source])
    if tags:
        cmd.extend(["--tags", tags])
    return _run(*cmd)


def _tool_list(args: dict) -> str:
    limit = args.get("limit", 20)
    source = args.get("source")
    cmd = ["list", "--limit", str(limit), "--json"]
    if source:
        cmd.extend(["--source", source])
    return _run(*cmd)


def _tool_get(args: dict) -> str:
    eid = args.get("id")
    if eid is None:
        return json.dumps({"error": "id is required"})
    return _run("get", str(eid), "--json")


def _tool_promote(args: dict) -> str:
    eid = args.get("id")
    if eid is None:
        return json.dumps({"error": "id is required"})
    return _run("promote", str(eid))


def _tool_compact(args: dict) -> str:
    return _run("compact")


def _tool_stats(args: dict) -> str:
    return _run("stats")


TOOLS: dict[str, dict] = {
    "wakayo_add": {
        "name": "wakayo_add",
        "description": (
            "Add an episodic memory entry to the shared wakayo store. "
            "Capture facts, decisions, observations, or anything worth "
            "remembering across sessions. Both opencode and Hermes write "
            "here — this is the shared brain."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The memory content to store."},
                "source": {
                    "type": "string",
                    "description": "Origin of the capture.",
                    "enum": ["opencode", "hermes", "manual"],
                },
                "tags": {"type": "string", "description": "Comma-separated tags for filtering."},
                "expires_days": {"type": "integer", "description": "Auto-expire after N days (optional)."},
            },
            "required": ["content"],
        },
    },
    "wakayo_query": {
        "name": "wakayo_query",
        "description": (
            "FTS5 search over the shared wakayo store. Returns matching entries "
            "with id, content, source, tags, and dates. Use to recall prior captures "
            "from either editor."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text (FTS5 MATCH)."},
                "source": {"type": "string", "description": "Filter by source (opencode, hermes, manual)."},
                "tags": {"type": "string", "description": "Filter by tag."},
                "limit": {"type": "integer", "description": "Max results (default 20)."},
            },
            "required": ["query"],
        },
    },
    "wakayo_list": {
        "name": "wakayo_list",
        "description": (
            "List recent entries in the shared wakayo store. Returns the N most "
            "recent entries with id, content, source, tags, and dates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max entries (default 20)."},
                "source": {"type": "string", "description": "Filter by source (opencode, hermes, manual)."},
            },
        },
    },
    "wakayo_get": {
        "name": "wakayo_get",
        "description": "Get a single entry by its id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Entry id."},
            },
            "required": ["id"],
        },
    },
    "wakayo_promote": {
        "name": "wakayo_promote",
        "description": (
            "Promote an entry to the standing layer: set the DB-only "
            "promoted=1 flag so it survives compaction. This does NOT write "
            "to ~/MEMORY.md — ~/MEMORY.md is a separate curated file kept by "
            "hand. Promote is a queryability/audit flag, not a file-write path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Entry id to promote."},
            },
            "required": ["id"],
        },
    },
    "wakayo_compact": {
        "name": "wakayo_compact",
        "description": "Expire stale entries past their TTL (lifecycle cleanup).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "wakayo_stats": {
        "name": "wakayo_stats",
        "description": "Show store statistics: total entries, chars, expired, promoted, by source.",
        "inputSchema": {"type": "object", "properties": {}},
    },
}

HANDLERS = {
    "wakayo_add": _tool_add,
    "wakayo_query": _tool_query,
    "wakayo_list": _tool_list,
    "wakayo_get": _tool_get,
    "wakayo_promote": _tool_promote,
    "wakayo_compact": _tool_compact,
    "wakayo_stats": _tool_stats,
}


def _send(obj: object) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _handle(msg: dict) -> None:
    method = msg.get("method", "")
    params = msg.get("params", {})
    req_id = msg.get("id")

    if method == "initialize":
        _send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "wakayo", "version": "0.1.0"},
            },
        })
        return

    if method == "notifications/initialized":
        return  # one-way ack

    if method == "tools/list":
        _send({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": list(TOOLS.values())},
        })
        return

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = HANDLERS.get(name)
        if handler is None:
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"unknown tool: {name}"},
            })
            return
        try:
            raw = handler(arguments)
            # try to parse as JSON for a structured result; else return as text
            try:
                parsed = json.loads(raw)
                content = [{"type": "json", "data": parsed}]
            except (json.JSONDecodeError, ValueError):
                content = [{"type": "text", "text": raw}]
            _send({"jsonrpc": "2.0", "id": req_id, "result": {"content": content}})
        except Exception as exc:
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            })
        return

    if method == "ping":
        _send({"jsonrpc": "2.0", "id": req_id, "result": "pong"})
        return

    _send({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    })


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle(msg)


if __name__ == "__main__":
    main()
