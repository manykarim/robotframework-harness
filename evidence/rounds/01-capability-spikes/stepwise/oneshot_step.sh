#!/usr/bin/env bash
# Approach C: one fresh `robotcode repl` per step, rehydrating Browser state from a standalone
# Playwright node process (Browser import arg playwright_process_port + auto_closing_level=KEEP).
#   oneshot_step.sh node-start DIR PORT | step DIR PORT 'cell' | node-stop DIR
set -u
RC=${RC:-/home/many/workspace/robotcode-experiments/.venv/bin/robotcode}
BROWSER_PKG=~/workspace/robotcode-experiments/.venv/lib/python3.13/site-packages/Browser
cmd=$1; D=$(realpath -m "$2")
case $cmd in
node-start)
  mkdir -p "$D"; PORT=$3
  ( cd "$BROWSER_PKG/.." && PLAYWRIGHT_BROWSERS_PATH=0 setsid node Browser/wrapper/index.js 127.0.0.1 "$PORT" </dev/null >"$D/node.log" 2>&1 & echo $! > "$D/node.pid" )
  until ss -ltn | grep -q ":$PORT "; do sleep 0.05; done; echo "node pid=$(cat "$D/node.pid") port=$PORT"
  ;;
step)
  PORT=$3; CELL=$4
  printf 'Import Library    Browser    auto_closing_level=KEEP    playwright_process_port=%s    timeout=10s\n%s\n' "$PORT" "$CELL" \
    | "$RC" repl --plain --no-history -d "$D" 2>&1 | tee "$D/last.txt" | grep -v "^\s*$"
  grep -q "\[ FAIL \]" "$D/last.txt" && { echo "== FAIL"; exit 1; } || { echo "== PASS"; exit 0; }
  ;;
node-stop)
  kill -TERM -- -"$(cat "$D/node.pid")" 2>/dev/null; sleep 1; kill -0 "$(cat "$D/node.pid")" 2>/dev/null && kill -KILL -- -"$(cat "$D/node.pid")"; echo "node stopped"
  ;;
esac
