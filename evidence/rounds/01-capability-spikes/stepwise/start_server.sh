#!/usr/bin/env bash
# start a repl-server in its own session; print its real PID (resolved via the listening port)
# usage: start_server.sh PORT OUTDIR [extra repl-server args...]
PORT=$1; OUT=$2; shift 2
RC=~/workspace/robotcode-experiments/.venv/bin/robotcode
mkdir -p "$OUT"
setsid "$RC" repl-server --tcp "$PORT" -d "$OUT" "$@" </dev/null >"$OUT.server.log" 2>&1 &
for i in $(seq 200); do P=$("$(dirname "$0")/portpid.sh" "$PORT"); [ -n "$P" ] && break; sleep 0.05; done
echo "$P"
