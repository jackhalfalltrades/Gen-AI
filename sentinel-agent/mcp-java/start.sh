#!/usr/bin/env bash
# Start the Java MCP on :8090 (needs Postgres on :5433).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$ROOT/.mcp.pid"
LOG="$ROOT/.mcp.log"
PORT=8090

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "MCP already listening on $PORT"
  exit 0
fi

cd "$ROOT"
nohup mvn -DskipTests spring-boot:run >"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "starting MCP (mvn pid $(cat "$PIDFILE")), log $LOG"

for _ in $(seq 1 90); do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "MCP up on $PORT"
    exit 0
  fi
  sleep 1
done

echo "MCP did not bind $PORT in 90s — last log lines:" >&2
tail -n 30 "$LOG" >&2
exit 1
