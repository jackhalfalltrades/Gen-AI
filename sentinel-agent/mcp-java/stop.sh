#!/usr/bin/env bash
# Stop whatever is serving the Java MCP on :8090.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$ROOT/.mcp.pid"
PORT=8090

stopped=0

if [[ -f "$PIDFILE" ]]; then
  pid="$(cat "$PIDFILE")"
  if kill -0 "$pid" 2>/dev/null; then
    # Maven leaves a child JVM; kill the process group.
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    stopped=1
  fi
  rm -f "$PIDFILE"
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  # -t can return several pids (mvn + java).
  # shellcheck disable=SC2046
  kill $(lsof -nP -t -iTCP:"$PORT" -sTCP:LISTEN) 2>/dev/null || true
  stopped=1
fi

sleep 1
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "still listening on $PORT" >&2
  exit 1
fi

if [[ "$stopped" -eq 1 ]]; then
  echo "MCP stopped"
else
  echo "MCP was not running"
fi
