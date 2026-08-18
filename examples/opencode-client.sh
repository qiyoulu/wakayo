#!/usr/bin/env bash
# opencode → wakayo: minimal bash client
# opencode can call this directly via its bash tool, or wrap it as an MCP server.

set -euo pipefail

WAKAYO="${WAKAYO_CLI:-wakayo}"
DIR="${WAKAYO_DIR:-}"

if [[ -n "$DIR" ]]; then
  export WAKAYO_DIR="$DIR"
fi

case "${1:-}" in
  add)
    shift
    "$WAKAYO" add "$@" ;;
  query)
    shift
    "$WAKAYO" query "$@" ;;
  list)
    "$WAKAYO" list "$@" ;;
  promote)
    "$WAKAYO" promote "$2" ;;
  compact)
    "$WAKAYO" compact ;;
  stats)
    "$WAKAYO" stats ;;
  *)
    echo "usage: wakayo-client add|query|list|promote|compact|stats" >&2
    exit 1 ;;
esac
